from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect

from app.remote_web_boundary import FORBIDDEN_CREDENTIAL_QUERY_KEYS, _allowed_web_app_origins, _normalized_host
from app.system.platform_identity import load_platform_identity
from app.system.security.roles import ROLE_PERMISSIONS
from app.system.settings.store import SettingsStore
from app.system.users.store import UsersStore

from .device_enrollment import WebAppEnrollmentStore
from .human import HumanPrincipal, authenticate_human_token
from .tokens import ServiceTokenKeyStore


def build_web_app_router(
    keys: ServiceTokenKeyStore,
    users: UsersStore,
    devices: WebAppEnrollmentStore,
    settings: SettingsStore,
    realtime_heartbeat_s: float = 30.0,
) -> APIRouter:
    router = APIRouter()

    async def enrolled_principal(authorization: str | None) -> tuple[HumanPrincipal, dict, object]:
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
        return principal, device, identity

    @router.get("/bootstrap")
    async def bootstrap(authorization: str | None = Header(default=None)):
        principal, device, identity = await enrolled_principal(authorization)

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
                "realtime": True,
                "notifications": False,
                "administration": "core.admin" in permissions,
            },
            "notifications": {
                "supported": False,
                "state": "not_implemented",
            },
        }

    async def close_for_auth_error(websocket: WebSocket, exc: HTTPException) -> None:
        code = 4401 if exc.status_code == 401 else 4403
        await websocket.close(code=code, reason=str(exc.detail)[:120])

    @router.websocket("/realtime")
    async def realtime(websocket: WebSocket):
        query_keys = {str(key).strip().lower() for key in websocket.query_params.keys()}
        if query_keys.intersection(FORBIDDEN_CREDENTIAL_QUERY_KEYS):
            await websocket.close(code=4400, reason="credentials_in_query_forbidden")
            return

        identity = await load_platform_identity(settings)
        host = _normalized_host(websocket.headers.get("host", ""))
        if host != identity.public_hostname.lower():
            await websocket.close(code=4403, reason="public_core_host_required")
            return
        origin = str(websocket.headers.get("origin") or "").strip()
        if origin and origin not in _allowed_web_app_origins(identity.public_hostname.lower()):
            await websocket.close(code=4403, reason="cors_origin_not_allowed")
            return

        authorization = websocket.headers.get("authorization")
        try:
            principal, _, _ = await enrolled_principal(authorization)
        except HTTPException as exc:
            await close_for_auth_error(websocket, exc)
            return

        await websocket.accept()
        await websocket.send_json(
            {
                "type": "realtime.ready",
                "contract_version": "hexe.remote-web-app.v1",
                "user_id": principal.user_id,
                "session_id": principal.session_id,
                "device_id": principal.device_id,
            }
        )
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(), timeout=realtime_heartbeat_s)
                except asyncio.TimeoutError:
                    try:
                        await enrolled_principal(authorization)
                    except HTTPException as exc:
                        await close_for_auth_error(websocket, exc)
                        return
                    await websocket.send_json({"type": "realtime.heartbeat"})
                    continue

                if len(raw.encode("utf-8")) > 16 * 1024:
                    await websocket.close(code=4400, reason="realtime_message_too_large")
                    return
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.close(code=4400, reason="realtime_message_invalid")
                    return
                if not isinstance(message, dict):
                    await websocket.close(code=4400, reason="realtime_message_invalid")
                    return

                message_type = str(message.get("type") or "")
                if message_type == "auth.renew":
                    candidate = str(message.get("access_token") or "")
                    try:
                        renewed, _, _ = await enrolled_principal(f"Bearer {candidate}" if candidate else None)
                    except HTTPException as exc:
                        await close_for_auth_error(websocket, exc)
                        return
                    if renewed.user_id != principal.user_id or renewed.device_id != principal.device_id:
                        await websocket.close(code=4403, reason="realtime_identity_change_forbidden")
                        return
                    authorization = f"Bearer {candidate}"
                    principal = renewed
                    await websocket.send_json({"type": "auth.renewed", "session_id": principal.session_id})
                    continue

                try:
                    principal, _, _ = await enrolled_principal(authorization)
                except HTTPException as exc:
                    await close_for_auth_error(websocket, exc)
                    return
                if message_type == "ping":
                    await websocket.send_json({"type": "pong"})
                else:
                    await websocket.send_json({"type": "error", "code": "realtime_message_type_unsupported"})
        except WebSocketDisconnect:
            return

    return router
