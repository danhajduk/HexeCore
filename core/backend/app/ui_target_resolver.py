from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

from fastapi import HTTPException

from app.ui_metadata import derive_node_api_base_url
from app.ui_targets import UiProxyTarget, validate_ui_proxy_target


ResolvedTargetSource = Literal["registered_remote", "embedded_local", "node_registration"]
ResolvedTargetSurface = Literal["ui", "api"]
ResolvedTargetKind = Literal["addon", "node"]


@dataclass(frozen=True)
class ResolvedProxyTarget:
    kind: ResolvedTargetKind
    target_id: str
    surface: ResolvedTargetSurface
    source: ResolvedTargetSource
    public_prefix: str
    target_base: str
    health_endpoint: str | None = None


def _text_attr(obj: object, name: str) -> str | None:
    value = str(getattr(obj, name, "") or "").strip()
    return value or None


def _node_api_base_url(node: object) -> str | None:
    runtime = getattr(node, "runtime", None)
    return derive_node_api_base_url(
        api_base_url=_text_attr(node, "api_base_url")
        or _text_attr(node, "requested_api_base_url")
        or _text_attr(runtime, "api_base_url"),
        ui_base_url=_text_attr(node, "ui_base_url") or _text_attr(runtime, "ui_base_url"),
        requested_ui_endpoint=_text_attr(node, "requested_ui_endpoint"),
        requested_hostname=_text_attr(node, "requested_hostname"),
    )


class UiTargetResolver:
    def __init__(self, *, addon_registry=None, nodes_service=None) -> None:
        self._addon_registry = addon_registry
        self._nodes_service = nodes_service

    def resolve_addon_ui(self, addon_id: str, *, request_base_url: str) -> ResolvedProxyTarget:
        if self._addon_registry is None:
            raise HTTPException(status_code=500, detail="addon_registry_unavailable")
        addon = self._addon_registry.registered.get(addon_id)
        if addon is not None:
            availability = validate_ui_proxy_target(
                UiProxyTarget(
                    kind="addon",
                    target_id=addon_id,
                    public_prefix=f"/addons/proxy/{addon_id}",
                    ui_enabled=bool(getattr(addon, "ui_enabled", False)),
                    ui_base_url=str(getattr(addon, "ui_base_url", "") or "").strip() or None,
                    ui_supports_prefix=getattr(addon, "ui_supports_prefix", None),
                    ui_entry_path=getattr(addon, "ui_entry_path", None),
                )
            )
            if not availability.available:
                raise HTTPException(status_code=availability.status_code, detail=availability.detail)
            return ResolvedProxyTarget(
                kind="addon",
                target_id=addon_id,
                surface="ui",
                source="registered_remote",
                public_prefix=f"/addons/proxy/{addon_id}",
                target_base=str(availability.ui_base_url or "").rstrip("/"),
            )
        if addon_id in self._addon_registry.addons:
            local_base = f"{str(request_base_url).rstrip('/')}/api/addons/{quote(addon_id, safe='')}"
            return ResolvedProxyTarget(
                kind="addon",
                target_id=addon_id,
                surface="ui",
                source="embedded_local",
                public_prefix=f"/addons/{addon_id}",
                target_base=local_base,
            )
        raise HTTPException(status_code=404, detail="registered_addon_not_found")

    def resolve_addon_api(self, addon_id: str, *, request_base_url: str) -> ResolvedProxyTarget:
        if self._addon_registry is None:
            raise HTTPException(status_code=500, detail="addon_registry_unavailable")
        addon = self._addon_registry.registered.get(addon_id)
        if addon is not None:
            return ResolvedProxyTarget(
                kind="addon",
                target_id=addon_id,
                surface="api",
                source="registered_remote",
                public_prefix=f"/api/addons/{addon_id}",
                target_base=str(addon.base_url).rstrip("/"),
            )
        if addon_id in self._addon_registry.addons:
            return ResolvedProxyTarget(
                kind="addon",
                target_id=addon_id,
                surface="api",
                source="embedded_local",
                public_prefix=f"/api/addons/{addon_id}",
                target_base=f"{str(request_base_url).rstrip('/')}/api/addons/{quote(addon_id, safe='')}",
            )
        raise HTTPException(status_code=404, detail="registered_addon_not_found")

    def resolve_node_ui(self, node_id: str) -> ResolvedProxyTarget:
        if self._nodes_service is None:
            raise HTTPException(status_code=500, detail="nodes_service_unavailable")
        node = self._nodes_service.get_node(node_id)
        availability = validate_ui_proxy_target(
            UiProxyTarget(
                kind="node",
                target_id=node_id,
                public_prefix=f"/nodes/proxy/{node_id}",
                ui_enabled=bool(getattr(node, "ui_enabled", False)),
                ui_base_url=str(getattr(node, "ui_base_url", "") or "").strip() or None,
                ui_health_endpoint=str(getattr(node, "ui_health_endpoint", "") or "").strip() or None,
                ui_supports_prefix=getattr(node, "ui_supports_prefix", None),
                ui_entry_path=getattr(node, "ui_entry_path", None),
            )
        )
        if not availability.available:
            raise HTTPException(status_code=availability.status_code, detail=availability.detail)
        return ResolvedProxyTarget(
            kind="node",
            target_id=node_id,
            surface="ui",
            source="node_registration",
            public_prefix=f"/nodes/proxy/{node_id}",
            target_base=str(availability.ui_base_url or "").rstrip("/"),
            health_endpoint=availability.ui_health_endpoint,
        )

    def resolve_node_api(self, node_id: str) -> ResolvedProxyTarget:
        if self._nodes_service is None:
            raise HTTPException(status_code=500, detail="nodes_service_unavailable")
        node = self._nodes_service.get_node(node_id)
        api_base = _node_api_base_url(node)
        if not api_base:
            raise HTTPException(status_code=404, detail="node_api_endpoint_not_configured")
        return ResolvedProxyTarget(
            kind="node",
            target_id=node_id,
            surface="api",
            source="node_registration",
            public_prefix=f"/api/nodes/{node_id}",
            target_base=api_base,
            health_endpoint=_text_attr(node, "ui_health_endpoint"),
        )
