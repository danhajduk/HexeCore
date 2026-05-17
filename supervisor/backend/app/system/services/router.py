from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.addons.registry import AddonRegistry
from app.system.auth import ServiceTokenClaims, ServiceTokenKeyStore, require_service_token
from app.system.events import PlatformEventService
from .store import ServiceCatalogStore


class ServiceRegisterRequest(BaseModel):
    service_type: str = Field(..., min_length=1)
    addon_id: str = Field(..., min_length=1)
    endpoint: str = Field(..., min_length=1)
    health: str = Field(default="unknown", min_length=1)
    capabilities: list[str] = Field(default_factory=list)
    service_id: str | None = None
    provider: str | None = None
    models: list[dict | str] = Field(default_factory=list)
    declared_capacity: dict = Field(default_factory=dict)
    auth_modes: list[str] = Field(default_factory=list)
    required_scopes: list[str] = Field(default_factory=list)


def build_service_resolution_router(
    registry: AddonRegistry,
    catalog_store: ServiceCatalogStore,
    key_store: ServiceTokenKeyStore,
    events: PlatformEventService | None = None,
) -> APIRouter:
    router = APIRouter()
    require_register_scope = require_service_token(
        key_store=key_store,
        audience="synthia-core",
        scopes=["services.register"],
    )

    @router.post("/register")
    async def register_service(
        body: ServiceRegisterRequest,
        claims: ServiceTokenClaims = Depends(require_register_scope),
    ):
        addon_id = body.addon_id.strip()
        service_type = body.service_type.strip()
        endpoint = body.endpoint.strip()
        health = body.health.strip().lower() or "unknown"
        capabilities = sorted({str(item).strip() for item in body.capabilities if str(item).strip()})
        if claims.sub != addon_id:
            raise HTTPException(status_code=403, detail="service_registration_subject_mismatch")
        if not registry.has_addon(addon_id):
            raise HTTPException(status_code=404, detail="service_registration_addon_not_found")

        local_addon = registry.addons.get(addon_id)
        remote_addon = registry.registered.get(addon_id)
        addon_name = local_addon.meta.name if local_addon else (remote_addon.name if remote_addon else addon_id)
        addon_version = local_addon.meta.version if local_addon else (remote_addon.version if remote_addon else "unknown")
        enabled = registry.is_enabled(addon_id)

        saved = await catalog_store.upsert_service(
            service_type=service_type,
            addon_id=addon_id,
            endpoint=endpoint,
            health=health,
            capabilities=capabilities,
            addon_registry={
                "addon_id": addon_id,
                "name": addon_name,
                "version": addon_version,
                "enabled": enabled,
                "registered_remote": remote_addon is not None,
                "loaded_local": local_addon is not None,
            },
            service_id=str(body.service_id or "").strip() or None,
            provider=str(body.provider or "").strip() or None,
            models=list(body.models or []),
            declared_capacity=dict(body.declared_capacity or {}),
            auth_modes=list(body.auth_modes or []),
            required_scopes=list(body.required_scopes or []),
        )
        if events is not None:
            await events.emit(
                event_type="service_registered",
                source="services.api",
                payload={
                    "service_type": service_type,
                    "addon_id": addon_id,
                        "endpoint": endpoint,
                        "health": health,
                        "capabilities": capabilities,
                        "provider": str(body.provider or "").strip() or None,
                    },
                )
        return {"ok": True, "service": saved}

    @router.get("/resolve")
    async def resolve_service(capability: str = Query(..., min_length=1)):
        for addon_id, addon in sorted(registry.addons.items(), key=lambda x: x[0]):
            if not registry.is_enabled(addon_id):
                continue
            if capability in addon.meta.capabilities:
                return {
                    "ok": True,
                    "source": "registry-local",
                    "service": capability,
                    "provider": {
                        "id": addon.meta.id,
                        "name": addon.meta.name,
                        "base_url": f"/api/addons/{addon.meta.id}",
                        "auth_mode": "none",
                        "health_status": "ok",
                        "last_seen": None,
                    },
                }

        for addon in sorted(registry.list_registered(), key=lambda x: x.id):
            if addon.health_status not in {"ok", "unknown"}:
                continue
            if capability in addon.capabilities:
                return {
                    "ok": True,
                    "source": "registry",
                    "service": capability,
                    "provider": {
                        "id": addon.id,
                        "name": addon.name,
                        "base_url": addon.base_url,
                        "auth_mode": addon.auth_mode,
                        "health_status": addon.health_status,
                        "last_seen": addon.last_seen,
                    },
                }

        catalog_item = await catalog_store.resolve(capability)
        if catalog_item is not None:
                return {
                    "ok": True,
                    "source": "catalog",
                    "service": capability,
                    "provider": catalog_item,
                }

        raise HTTPException(status_code=404, detail="service_provider_not_found")

    return router
