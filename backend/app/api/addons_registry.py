from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ..addons.registry import AddonRegistry
from .admin import require_admin_token


class RegisterAddonRequest(BaseModel):
    base_url: str = Field(..., min_length=1)
    name: str | None = None
    version: str | None = None


class ConfigureAddonRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


def build_addons_registry_router(registry: AddonRegistry) -> APIRouter:
    router = APIRouter()

    @router.get("/addons/registry")
    def list_registry():
        return [item.model_dump(mode="json") for item in registry.list_registered()]

    @router.get("/addons/registry/{addon_id}")
    def get_registry_item(addon_id: str):
        addon = registry.registered.get(addon_id)
        if addon is None:
            raise HTTPException(status_code=404, detail="addon_not_found")
        return addon.model_dump(mode="json")

    @router.post("/addons/registry/{addon_id}/register")
    async def register_registry_item(
        addon_id: str,
        body: RegisterAddonRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ):
        require_admin_token(x_admin_token, request)
        saved = await registry.register_remote(
            addon_id=addon_id,
            base_url=body.base_url.strip(),
            name=body.name.strip() if body.name else None,
            version=body.version.strip() if body.version else None,
        )
        return {"ok": True, "addon": saved.model_dump(mode="json")}

    @router.post("/addons/registry/{addon_id}/configure")
    async def configure_registry_item(
        addon_id: str,
        body: ConfigureAddonRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ):
        require_admin_token(x_admin_token, request)
        try:
            payload = await registry.configure_registered(addon_id, body.config)
        except KeyError:
            raise HTTPException(status_code=404, detail="addon_not_found")
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        return {"ok": True, "addon_id": addon_id, "result": payload}

    @router.post("/addons/registry/{addon_id}/verify")
    async def verify_registry_item(
        addon_id: str,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ):
        require_admin_token(x_admin_token, request)
        try:
            payload = await registry.verify_registered(addon_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="addon_not_found")
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        addon = registry.registered.get(addon_id)
        return {
            "ok": True,
            "addon_id": addon_id,
            "status": addon.health_status if addon is not None else "unknown",
            "health": payload,
        }

    return router
