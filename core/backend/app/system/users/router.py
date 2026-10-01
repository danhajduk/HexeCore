from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.admin import admin_request_actor, require_admin_token
from app.system.audit import AuditLogStore
from app.system.security import AuthRole
from app.system.auth.human import authenticate_human_token
from app.system.auth.tokens import ServiceTokenKeyStore
from .store import UsersStore

if TYPE_CHECKING:
    from app.system.auth.device_enrollment import WebAppEnrollmentStore


class UserUpsertRequest(BaseModel):
    username: str = Field(..., min_length=1)
    role: str = Field(default="guest")
    enabled: bool = True
    password: str | None = None


def build_users_router(users_store: UsersStore, audit_store: AuditLogStore | None = None, key_store: ServiceTokenKeyStore | None = None, devices_store: WebAppEnrollmentStore | None = None) -> APIRouter:
    router = APIRouter()

    async def require_user_admin(request: Request, x_admin_token: str | None, authorization: str | None):
        if authorization and key_store is not None:
            principal = await authenticate_human_token(authorization, key_store, users_store)
            principal.require("users.manage")
            return principal.user_id, principal.role
        require_admin_token(x_admin_token, request)
        actor_id, actor_role = admin_request_actor(request)
        actor = await users_store.get_user(actor_id)
        if actor is not None and str(actor.get("role")) in {AuthRole.owner.value, AuthRole.admin.value}:
            return str(actor["user_id"]), str(actor["role"])
        return actor_id, actor_role

    @router.get("/users")
    async def list_users(request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        await require_user_admin(request, x_admin_token, authorization)
        return {"ok": True, "items": await users_store.list_users()}

    @router.post("/users")
    async def upsert_user(body: UserUpsertRequest, request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_id, actor_role = await require_user_admin(request, x_admin_token, authorization)
        existing = await users_store.get_user(body.username)
        if actor_role != AuthRole.owner.value and (
            body.role.strip().lower() == AuthRole.owner.value
            or (existing is not None and str(existing.get("role")) == AuthRole.owner.value)
        ):
            raise HTTPException(status_code=403, detail="owner_role_required")
        try:
            saved = await users_store.upsert_user(
                username=body.username,
                role=body.role,
                enabled=bool(body.enabled),
                password=body.password,
            )
        except Exception as exc:
            msg = str(exc) or type(exc).__name__
            raise HTTPException(status_code=400, detail=msg)

        disabled_device_count = 0
        if existing is not None and bool(existing.get("enabled")) and not bool(saved.get("enabled")):
            await users_store.revoke_user_sessions(str(saved["user_id"]), reason="user_disabled")
            if devices_store is not None:
                disabled_device_count = await devices_store.disable_user_devices(str(saved["user_id"]))

        if audit_store is not None:
            await audit_store.record(
                event_type="admin_user_upsert",
                actor_role=actor_role,
                actor_id=actor_id,
                details={"username": saved["username"], "role": saved["role"], "enabled": saved["enabled"]},
            )
            if existing is not None and str(existing.get("role")) != str(saved.get("role")):
                await audit_store.record(event_type="human_role_changed", actor_role=actor_role, actor_id=actor_id, details={"user_id": saved["user_id"], "old_role": existing["role"], "new_role": saved["role"]})
            if existing is not None and bool(existing.get("enabled")) != bool(saved.get("enabled")):
                await audit_store.record(event_type="human_user_enabled_changed", actor_role=actor_role, actor_id=actor_id, details={"user_id": saved["user_id"], "enabled": saved["enabled"]})
            if existing is not None and body.password:
                await audit_store.record(event_type="human_password_changed", actor_role=actor_role, actor_id=actor_id, details={"user_id": saved["user_id"]})
        return {"ok": True, "user": saved, "disabled_device_count": disabled_device_count}

    @router.get("/users/{username}/sessions")
    async def list_user_sessions(username: str, request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        await require_user_admin(request, x_admin_token, authorization)
        user = await users_store.get_user(username)
        if user is None:
            raise HTTPException(status_code=404, detail="user_not_found")
        return {"ok": True, "user_id": user["user_id"], "items": await users_store.list_sessions(str(user["user_id"]))}

    @router.delete("/users/{username}/sessions/{session_id}")
    async def revoke_user_session(username: str, session_id: str, request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_id, actor_role = await require_user_admin(request, x_admin_token, authorization)
        user = await users_store.get_user(username)
        if user is None:
            raise HTTPException(status_code=404, detail="user_not_found")
        if not await users_store.revoke_session(session_id, reason="administrator_revoked", user_id=str(user["user_id"])):
            raise HTTPException(status_code=404, detail="session_not_found")
        if audit_store is not None:
            await audit_store.record(event_type="human_session_revoked", actor_role=actor_role, actor_id=actor_id, details={"user_id": user["user_id"], "session_id": session_id})
        return {"ok": True, "session_id": session_id}

    @router.delete("/users/{username}")
    async def delete_user(username: str, request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_id, actor_role = await require_user_admin(request, x_admin_token, authorization)
        existing = await users_store.get_user(username)
        if existing is not None and str(existing.get("role")) == AuthRole.owner.value and actor_role != AuthRole.owner.value:
            raise HTTPException(status_code=403, detail="owner_role_required")
        try:
            deleted = await users_store.delete_user(username)
        except Exception as exc:
            msg = str(exc) or type(exc).__name__
            raise HTTPException(status_code=400, detail=msg)
        if not deleted:
            raise HTTPException(status_code=404, detail="user_not_found")

        disabled_device_count = 0
        if existing is not None:
            await users_store.revoke_user_sessions(str(existing["user_id"]), reason="user_deleted")
            if devices_store is not None:
                disabled_device_count = await devices_store.disable_user_devices(str(existing["user_id"]))

        if audit_store is not None:
            await audit_store.record(
                event_type="admin_user_delete",
                actor_role=actor_role,
                actor_id=actor_id,
                details={"username": username},
            )
        return {"ok": True, "username": username, "disabled_device_count": disabled_device_count}

    return router
