from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.admin import require_admin_token
from app.system.audit import AuditLogStore
from app.system.security import AuthRole
from .store import UsersStore


class UserUpsertRequest(BaseModel):
    username: str = Field(..., min_length=1)
    role: str = Field(default="guest")
    enabled: bool = True
    password: str | None = None


def build_users_router(users_store: UsersStore, audit_store: AuditLogStore | None = None) -> APIRouter:
    router = APIRouter()

    @router.get("/users")
    async def list_users(request: Request, x_admin_token: str | None = Header(default=None)):
        require_admin_token(x_admin_token, request)
        return {"ok": True, "items": await users_store.list_users()}

    @router.post("/users")
    async def upsert_user(body: UserUpsertRequest, request: Request, x_admin_token: str | None = Header(default=None)):
        require_admin_token(x_admin_token, request)
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

        if audit_store is not None:
            await audit_store.record(
                event_type="admin_user_upsert",
                actor_role=AuthRole.admin.value,
                actor_id="admin_session",
                details={"username": saved["username"], "role": saved["role"], "enabled": saved["enabled"]},
            )
        return {"ok": True, "user": saved}

    @router.delete("/users/{username}")
    async def delete_user(username: str, request: Request, x_admin_token: str | None = Header(default=None)):
        require_admin_token(x_admin_token, request)
        try:
            deleted = await users_store.delete_user(username)
        except Exception as exc:
            msg = str(exc) or type(exc).__name__
            raise HTTPException(status_code=400, detail=msg)
        if not deleted:
            raise HTTPException(status_code=404, detail="user_not_found")

        if audit_store is not None:
            await audit_store.record(
                event_type="admin_user_delete",
                actor_role=AuthRole.admin.value,
                actor_id="admin_session",
                details={"username": username},
            )
        return {"ok": True, "username": username}

    return router
