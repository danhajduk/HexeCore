from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.addons.registry import AddonRegistry
from .store import ServiceCatalogStore


def build_service_resolution_router(
    registry: AddonRegistry,
    catalog_store: ServiceCatalogStore,
) -> APIRouter:
    router = APIRouter()

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
