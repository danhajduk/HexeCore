from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException

from app.system.audit import AuditLogStore
from app.system.onboarding import NodeRegistrationsStore
from app.system.platform_identity import (
    PlatformIdentity,
    derive_public_api_hostname,
    derive_public_ui_hostname,
    is_valid_core_id,
    load_platform_identity,
)
from app.supervisor.service import SupervisorDomainService

from .cloudflare_renderer import CloudflareConfigRenderer
from .models import (
    CloudflareSettings,
    CorePublicIdentity,
    EdgeDryRunResult,
    EdgePublication,
    EdgePublicationCreateRequest,
    EdgePublicationUpdateRequest,
    EdgeStatus,
    EdgeTargetHealth,
    EdgeTunnelStatus,
    utcnow_iso,
)
from .store import EdgeGatewayStore

HOSTNAME_PATTERN = re.compile(r"^[a-z0-9.-]+$")


class EdgeGatewayService:
    def __init__(
        self,
        store: EdgeGatewayStore,
        *,
        settings_store=None,
        node_registrations_store: NodeRegistrationsStore | None = None,
        supervisor_service: SupervisorDomainService | None = None,
        renderer: CloudflareConfigRenderer | None = None,
        audit_store: AuditLogStore | None = None,
    ) -> None:
        self._store = store
        self._settings_store = settings_store
        self._node_registrations_store = node_registrations_store
        self._supervisor_service = supervisor_service
        self._renderer = renderer or CloudflareConfigRenderer()
        self._audit_store = audit_store

    async def public_identity(self) -> CorePublicIdentity:
        identity = await load_platform_identity(self._settings_store)
        return CorePublicIdentity(
            core_id=identity.core_id,
            core_name=identity.core_name,
            platform_domain=identity.platform_domain,
            public_ui_hostname=identity.public_ui_hostname,
            public_api_hostname=identity.public_api_hostname,
        )

    async def get_cloudflare_settings(self) -> CloudflareSettings:
        return await self._store.get_cloudflare_settings()

    async def update_cloudflare_settings(self, settings: CloudflareSettings) -> CloudflareSettings:
        self._validate_cloudflare_settings(settings)
        saved = await self._store.set_cloudflare_settings(settings.model_copy(update={"updated_at": utcnow_iso()}))
        await self._audit(
            "edge_cloudflare_settings_updated",
            {"enabled": saved.enabled, "zone_id": saved.zone_id, "tunnel_id": saved.tunnel_id},
        )
        return saved

    async def list_publications(self) -> list[EdgePublication]:
        identity = await self.public_identity()
        publications = await self._store.list_publications()
        return self._inject_core_publications(publications, identity)

    async def create_publication(self, body: EdgePublicationCreateRequest) -> EdgePublication:
        publications = await self._store.list_publications()
        publication = EdgePublication(
            publication_id=f"edgepub-{len(publications)+1}",
            hostname=body.hostname.strip().lower(),
            path_prefix=body.path_prefix,
            enabled=body.enabled,
            source=body.source,
            target=body.target,
        )
        identity = await self.public_identity()
        self._validate_publication(publication, publications, identity)
        publications.append(publication)
        await self._store.set_publications(publications)
        await self._audit(
            "edge_publication_created",
            {"publication_id": publication.publication_id, "hostname": publication.hostname, "target_type": publication.target.target_type},
        )
        return publication

    async def update_publication(self, publication_id: str, body: EdgePublicationUpdateRequest) -> EdgePublication:
        publications = await self._store.list_publications()
        target_index = next((idx for idx, item in enumerate(publications) if item.publication_id == publication_id), None)
        if target_index is None:
            raise HTTPException(status_code=404, detail="edge_publication_not_found")
        current = publications[target_index]
        updated = current.model_copy(
            update={
                key: value
                for key, value in {
                    "hostname": body.hostname.strip().lower() if isinstance(body.hostname, str) else None,
                    "path_prefix": body.path_prefix,
                    "enabled": body.enabled,
                    "source": body.source,
                    "target": body.target,
                    "updated_at": utcnow_iso(),
                }.items()
                if value is not None
            }
        )
        remaining = [item for idx, item in enumerate(publications) if idx != target_index]
        identity = await self.public_identity()
        self._validate_publication(updated, remaining, identity)
        publications[target_index] = updated
        await self._store.set_publications(publications)
        await self._audit(
            "edge_publication_updated",
            {"publication_id": updated.publication_id, "hostname": updated.hostname, "enabled": updated.enabled},
        )
        return updated

    async def delete_publication(self, publication_id: str) -> None:
        publications = await self._store.list_publications()
        updated = [item for item in publications if item.publication_id != publication_id]
        await self._store.set_publications(updated)
        await self._audit("edge_publication_deleted", {"publication_id": publication_id})

    async def dry_run(self) -> EdgeDryRunResult:
        identity = await self.public_identity()
        settings = await self._store.get_cloudflare_settings()
        publications = await self._store.list_publications()
        validation_errors = self._collect_validation_errors(identity, settings, publications)
        rendered = self._renderer.render(identity=identity, settings=settings, publications=publications)
        return EdgeDryRunResult(
            ok=not validation_errors,
            public_identity=identity,
            validation_errors=validation_errors,
            rendered_config=rendered,
        )

    async def reconcile(self) -> dict[str, object]:
        dry_run = await self.dry_run()
        status = await self._store.get_tunnel_status()
        reconcile_state: dict[str, object] = {
            "last_reconcile_at": utcnow_iso(),
            "last_status": "ok" if dry_run.ok else "error",
            "last_error": None if dry_run.ok else "; ".join(dry_run.validation_errors),
        }
        if dry_run.ok and self._supervisor_service is not None:
            rendered = dict(dry_run.rendered_config)
            apply_result = self._supervisor_service.apply_cloudflared_config(rendered)
            status = status.model_copy(
                update={
                    "configured": True,
                    "runtime_state": str(apply_result.get("runtime_state") or "configured"),
                    "healthy": bool(apply_result.get("ok")),
                    "config_path": str(apply_result.get("config_path") or ""),
                    "last_error": None if bool(apply_result.get("ok")) else str(apply_result.get("error") or "unknown"),
                    "updated_at": utcnow_iso(),
                }
            )
            await self._store.set_tunnel_status(status)
            reconcile_state["supervisor"] = apply_result
        else:
            status = status.model_copy(update={"updated_at": utcnow_iso()})
            await self._store.set_tunnel_status(status)
        await self._store.set_reconcile_state(reconcile_state)
        await self._audit(
            "edge_reconcile_completed",
            {"status": reconcile_state.get("last_status"), "error": reconcile_state.get("last_error")},
        )
        return reconcile_state

    async def status(self) -> EdgeStatus:
        identity = await self.public_identity()
        settings = await self._store.get_cloudflare_settings()
        publications = await self.list_publications()
        tunnel = await self._store.get_tunnel_status()
        reconcile_state = await self._store.get_reconcile_state()
        target_health = self._target_health(publications)
        validation_errors = self._collect_validation_errors(identity, settings, await self._store.list_publications())
        return EdgeStatus(
            public_identity=identity,
            cloudflare=settings,
            tunnel=tunnel,
            publications=publications,
            target_health=target_health,
            reconcile_state=reconcile_state,
            validation_errors=validation_errors,
        )

    def _target_health(self, publications: list[EdgePublication]) -> list[EdgeTargetHealth]:
        health: list[EdgeTargetHealth] = []
        for item in publications:
            detail = None
            state = "healthy"
            if item.target.target_type == "node":
                node = self._node_registrations_store.get(item.target.target_id) if self._node_registrations_store is not None else None
                if node is None or node.trust_status != "trusted":
                    state = "unavailable"
                    detail = "node_not_trusted"
            elif item.target.target_type == "supervisor_runtime" and self._supervisor_service is not None:
                runtime = self._supervisor_service.get_runtime_state(item.target.target_id)
                if not runtime.get("exists"):
                    state = "unavailable"
                    detail = "runtime_not_found"
            parsed = urlsplit(item.target.upstream_base_url)
            if parsed.hostname not in {"127.0.0.1", "localhost"}:
                state = "degraded"
                detail = "host_not_allowlisted"
            health.append(
                EdgeTargetHealth(
                    target_type=item.target.target_type,
                    target_id=item.target.target_id,
                    state=state,
                    detail=detail,
                )
            )
        return health

    def _inject_core_publications(
        self,
        publications: list[EdgePublication],
        identity: CorePublicIdentity,
    ) -> list[EdgePublication]:
        builtins = [
            EdgePublication(
                publication_id="core-ui",
                hostname=identity.public_ui_hostname,
                path_prefix="/",
                enabled=True,
                source="core_owned",
                target={
                    "target_type": "core_ui",
                    "target_id": "core-ui",
                    "upstream_base_url": "http://127.0.0.1:8080",
                    "allowed_path_prefixes": ["/"],
                },
            ),
            EdgePublication(
                publication_id="core-api",
                hostname=identity.public_api_hostname,
                path_prefix="/",
                enabled=True,
                source="core_owned",
                target={
                    "target_type": "core_api",
                    "target_id": "core-api",
                    "upstream_base_url": "http://127.0.0.1:9001",
                    "allowed_path_prefixes": ["/"],
                },
            ),
        ]
        return builtins + sorted(publications, key=lambda item: (item.hostname, item.path_prefix, item.publication_id))

    def _collect_validation_errors(
        self,
        identity: CorePublicIdentity,
        settings: CloudflareSettings,
        publications: list[EdgePublication],
    ) -> list[str]:
        errors: list[str] = []
        if not is_valid_core_id(identity.core_id):
            errors.append("core_id_invalid")
        if settings.enabled:
            try:
                self._validate_cloudflare_settings(settings)
            except HTTPException as exc:
                errors.append(str(exc.detail))
        for publication in publications:
            try:
                self._validate_publication(publication, [item for item in publications if item.publication_id != publication.publication_id], identity)
            except HTTPException as exc:
                errors.append(f"{publication.publication_id}:{exc.detail}")
        return errors

    def _validate_cloudflare_settings(self, settings: CloudflareSettings) -> None:
        if settings.enabled and not all([settings.account_id, settings.zone_id, settings.tunnel_id, settings.tunnel_name]):
            raise HTTPException(status_code=400, detail="cloudflare_settings_incomplete")
        if str(settings.managed_domain_base or "").strip().lower() != "hexe-ai.com":
            raise HTTPException(status_code=400, detail="cloudflare_domain_base_invalid")

    def _validate_publication(
        self,
        publication: EdgePublication,
        existing: list[EdgePublication],
        identity: CorePublicIdentity,
    ) -> None:
        hostname = str(publication.hostname or "").strip().lower()
        if not HOSTNAME_PATTERN.fullmatch(hostname):
            raise HTTPException(status_code=400, detail="edge_publication_hostname_invalid")
        if not hostname.endswith(f".{identity.platform_domain}"):
            raise HTTPException(status_code=400, detail="edge_publication_domain_invalid")
        if publication.source == "core_owned" and hostname not in {identity.public_ui_hostname, identity.public_api_hostname}:
            raise HTTPException(status_code=400, detail="edge_core_hostname_spoofed")
        if publication.target.target_type == "node":
            node = self._node_registrations_store.get(publication.target.target_id) if self._node_registrations_store is not None else None
            if node is None or node.trust_status != "trusted":
                raise HTTPException(status_code=400, detail="edge_target_node_not_trusted")
        if publication.target.target_type == "supervisor_runtime" and self._supervisor_service is not None:
            runtime = self._supervisor_service.get_runtime_state(publication.target.target_id)
            if not runtime.get("exists"):
                raise HTTPException(status_code=400, detail="edge_target_runtime_not_found")
        parsed = urlsplit(publication.target.upstream_base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise HTTPException(status_code=400, detail="edge_target_upstream_not_allowed")
        for item in existing:
            if item.hostname == hostname and item.path_prefix == publication.path_prefix:
                raise HTTPException(status_code=409, detail="edge_publication_conflict")

    async def _audit(self, event_type: str, details: dict[str, object]) -> None:
        if self._audit_store is None:
            return
        await self._audit_store.record(
            event_type=event_type,
            actor_role="admin",
            actor_id="edge_gateway",
            details=details,
        )
