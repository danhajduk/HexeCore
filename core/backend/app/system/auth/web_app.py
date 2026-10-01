from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.system.platform_identity import load_platform_identity
from app.system.security.roles import ROLE_PERMISSIONS
from app.system.settings.store import SettingsStore
from app.system.users.store import UsersStore

from .device_enrollment import WebAppEnrollmentStore
from .human import authenticate_human_token
from .tokens import ServiceTokenKeyStore


def build_web_app_router(
    keys: ServiceTokenKeyStore,
    users: UsersStore,
    devices: WebAppEnrollmentStore,
    settings: SettingsStore,
) -> APIRouter:
    router = APIRouter()

    @router.get("/bootstrap")
    async def bootstrap(authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        if not principal.device_id:
            raise HTTPException(status_code=403, detail="enrolled_device_required")

        device = await devices.get_device(principal.device_id)
        if (
            device is None
            or device.get("revoked_at")
            or str(device.get("user_id") or "") != principal.user_id
        ):
            raise HTTPException(status_code=403, detail="enrolled_device_invalid")

        identity = await load_platform_identity(settings)
        if str(device.get("core_id") or "") != identity.core_id:
            raise HTTPException(status_code=403, detail="enrolled_device_wrong_core")

        permissions = sorted(ROLE_PERMISSIONS.get(principal.role, frozenset()))
        return {
            "contract_version": "hexe.remote-web-app.v1",
            "core": {
                "core_id": identity.core_id,
                "core_name": identity.core_name,
                "public_hostname": identity.public_hostname,
            },
            "user": {
                "user_id": principal.user_id,
                "username": principal.username,
                "role": principal.role,
                "permissions": permissions,
            },
            "session": {"session_id": principal.session_id},
            "device": {
                "device_id": str(device["device_id"]),
                "display_name": str(device["display_name"]),
                "platform": device.get("platform"),
            },
            "features": {
                "assistant": False,
                "realtime": False,
                "notifications": False,
                "administration": "core.admin" in permissions,
            },
            "notifications": {
                "supported": False,
                "state": "not_implemented",
            },
        }

    return router
