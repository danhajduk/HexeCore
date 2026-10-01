from __future__ import annotations

import hashlib
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.system.audit import AuditLogStore
from app.system.security.roles import role_has_permission
from .tokens import ServiceTokenError, ServiceTokenKeyStore, sign_hs256, verify_hs256

if TYPE_CHECKING:
    from app.system.users.store import UsersStore

ACCESS_TTL_S = 10 * 60
REFRESH_TTL_S = 30 * 24 * 60 * 60


def _core_id() -> str:
    return str(os.getenv("HEXE_CORE_ID", "hexe-core")).strip() or "hexe-core"


def _issuer() -> str:
    return f"hexe-core:{_core_id()}"


def _audience() -> str:
    return f"hexe-core:{_core_id()}:web-app"


def _refresh_verifier(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _iso_after(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


@dataclass(frozen=True)
class HumanPrincipal:
    user_id: str
    username: str
    role: str
    session_id: str
    device_id: str | None

    def require(self, permission: str) -> None:
        if not role_has_permission(self.role, permission):
            raise HTTPException(status_code=403, detail="permission_denied")


class HumanLoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    device_id: str | None = Field(default=None, max_length=160)


class HumanRefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=32)


async def _access_token(key_store: ServiceTokenKeyStore, user: dict[str, object], session: dict[str, object]) -> tuple[str, dict[str, object]]:
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": _issuer(), "sub": str(user["user_id"]), "aud": _audience(),
        "role": str(user["role"]), "session_id": str(session["session_id"]),
        "sid": str(session["session_id"]), "device_id": session.get("device_id"),
        "credential_revision": int(user["credential_revision"]), "iat": now,
        "nbf": now, "exp": now + ACCESS_TTL_S, "jti": secrets.token_urlsafe(18),
        "token_use": "human_access",
    }
    key = await key_store.active_key()
    token = sign_hs256({"alg": "HS256", "typ": "JWT", "kid": str(key["kid"])}, claims, str(key["secret"]))
    await key_store.record_token_expiry(kid=str(key["kid"]), exp=int(claims["exp"]))
    return token, claims


async def authenticate_human_token(authorization: str | None, key_store: ServiceTokenKeyStore, users: UsersStore) -> HumanPrincipal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="human_access_token_missing")
    try:
        _, claims = verify_hs256(authorization.split(" ", 1)[1].strip(), await key_store.verification_keys())
    except ServiceTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    now = int(time.time())
    if claims.get("iss") != _issuer() or claims.get("aud") != _audience() or claims.get("token_use") != "human_access":
        raise HTTPException(status_code=401, detail="human_access_token_invalid")
    if not isinstance(claims.get("exp"), int) or int(claims["exp"]) <= now or int(claims.get("nbf") or 0) > now:
        raise HTTPException(status_code=401, detail="human_access_token_expired")
    user_id, session_id = str(claims.get("sub") or ""), str(claims.get("session_id") or "")
    user, session = await users.get_user_by_id(user_id), await users.get_session(session_id)
    if user is None or not bool(user.get("enabled")) or session is None or session.get("revoked_at"):
        raise HTTPException(status_code=401, detail="human_session_revoked")
    try:
        if datetime.fromisoformat(str(session.get("expires_at") or "").replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="human_session_expired")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="human_session_expired") from exc
    if str(session.get("user_id")) != user_id or int(user.get("credential_revision") or 0) != int(claims.get("credential_revision") or -1) or str(user.get("role")) != str(claims.get("role")):
        raise HTTPException(status_code=401, detail="human_session_stale")
    return HumanPrincipal(user_id, str(user["username"]), str(user["role"]), session_id, session.get("device_id") or None)


def build_human_auth_router(key_store: ServiceTokenKeyStore, users: UsersStore, audit: AuditLogStore | None = None) -> APIRouter:
    router = APIRouter()

    async def record(event_type: str, actor_id: str, role: str, details: dict[str, object]) -> None:
        if audit is not None:
            await audit.record(event_type=event_type, actor_role=role, actor_id=actor_id, details=details)

    @router.post("/user/login")
    async def login(body: HumanLoginRequest):
        user = await users.verify_credentials(body.username, body.password)
        if user is None:
            await record("human_login_failed", "anonymous", "guest", {"username": body.username.strip()})
            raise HTTPException(status_code=401, detail="invalid_credentials")
        refresh = secrets.token_urlsafe(48)
        session = await users.create_session(user_id=str(user["user_id"]), device_id=body.device_id, refresh_verifier=_refresh_verifier(refresh), expires_at=_iso_after(REFRESH_TTL_S))
        access, claims = await _access_token(key_store, user, session)
        await record("human_login_succeeded", str(user["user_id"]), str(user["role"]), {"session_id": session["session_id"], "device_id": body.device_id})
        return {"ok": True, "access_token": access, "refresh_token": refresh, "token_type": "bearer", "expires_in": ACCESS_TTL_S, "claims": claims, "user": user}

    @router.post("/user/refresh")
    async def refresh(body: HumanRefreshRequest):
        replacement = secrets.token_urlsafe(48)
        status, session = await users.rotate_session_refresh(refresh_verifier=_refresh_verifier(body.refresh_token), replacement_verifier=_refresh_verifier(replacement), expires_at=_iso_after(REFRESH_TTL_S))
        if status == "reused":
            await record("human_refresh_reuse_detected", "unknown", "guest", {})
            raise HTTPException(status_code=401, detail="refresh_token_reused")
        if status != "ok" or session is None:
            raise HTTPException(status_code=401, detail="refresh_token_invalid")
        user = await users.get_user_by_id(str(session["user_id"]))
        if user is None:
            raise HTTPException(status_code=401, detail="refresh_token_invalid")
        access, claims = await _access_token(key_store, user, session)
        await record("human_refresh_succeeded", str(user["user_id"]), str(user["role"]), {"session_id": session["session_id"]})
        return {"ok": True, "access_token": access, "refresh_token": replacement, "token_type": "bearer", "expires_in": ACCESS_TTL_S, "claims": claims}

    @router.get("/user/sessions")
    async def list_sessions(authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, key_store, users)
        return {"ok": True, "items": await users.list_sessions(principal.user_id), "current_session_id": principal.session_id}

    @router.post("/user/logout")
    async def logout(authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, key_store, users)
        await users.revoke_session(principal.session_id, reason="logout", user_id=principal.user_id)
        await record("human_logout", principal.user_id, principal.role, {"session_id": principal.session_id})
        return {"ok": True}

    @router.delete("/user/sessions/{session_id}")
    async def revoke_session(session_id: str, authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, key_store, users)
        if not await users.revoke_session(session_id, reason="user_revoked", user_id=principal.user_id):
            raise HTTPException(status_code=404, detail="session_not_found")
        await record("human_session_revoked", principal.user_id, principal.role, {"session_id": session_id})
        return {"ok": True, "session_id": session_id}

    return router
