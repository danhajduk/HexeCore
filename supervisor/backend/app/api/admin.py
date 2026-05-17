from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel

router = APIRouter()

if TYPE_CHECKING:
    from app.system.users import UsersStore

LOG_FILE = Path("/tmp/synthia_update.log")
ADMIN_SESSION_COOKIE = "synthia_admin_session"
DEFAULT_SESSION_TTL_SECONDS = 8 * 60 * 60
_users_store: "UsersStore | None" = None


class AdminSessionLoginRequest(BaseModel):
    token: str


class AdminUserSessionLoginRequest(BaseModel):
    username: str
    password: str


def configure_admin_users_store(store: "UsersStore | None") -> None:
    global _users_store
    _users_store = store


def _admin_token_expected() -> str:
    return os.getenv("SYNTHIA_ADMIN_TOKEN", "")


def _cookie_secure() -> bool:
    raw = os.getenv("SYNTHIA_ADMIN_COOKIE_SECURE", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _session_ttl_seconds() -> int:
    raw = os.getenv("SYNTHIA_ADMIN_SESSION_TTL_SECONDS", "").strip()
    try:
        parsed = int(raw) if raw else DEFAULT_SESSION_TTL_SECONDS
    except Exception:
        parsed = DEFAULT_SESSION_TTL_SECONDS
    return min(max(parsed, 300), 7 * 24 * 60 * 60)


def _session_secret(expected_token: str) -> str:
    configured = os.getenv("SYNTHIA_ADMIN_SESSION_SECRET", "")
    if configured:
        return configured
    if expected_token:
        return f"admin-session:{expected_token}"
    return "admin-session:local"


def _session_signature(payload: str, *, expected_token: str) -> str:
    secret = _session_secret(expected_token).encode("utf-8")
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _build_session_cookie(*, expected_token: str) -> tuple[str, int]:
    expires_at = int(time.time()) + _session_ttl_seconds()
    nonce = secrets.token_urlsafe(18)
    payload = f"{expires_at}:{nonce}"
    sig = _session_signature(payload, expected_token=expected_token)
    return f"{payload}:{sig}", expires_at


def _is_valid_session_cookie(cookie_value: str | None, *, expected_token: str) -> bool:
    if not cookie_value:
        return False
    parts = cookie_value.split(":")
    if len(parts) != 3:
        return False
    expires_raw, nonce, sig = parts
    if not nonce:
        return False
    try:
        expires_at = int(expires_raw)
    except Exception:
        return False
    if expires_at <= int(time.time()):
        return False
    payload = f"{expires_raw}:{nonce}"
    expected_sig = _session_signature(payload, expected_token=expected_token)
    return hmac.compare_digest(sig, expected_sig)


def require_admin_token(x_admin_token: str | None, request: Request | None = None) -> None:
    expected = _admin_token_expected()
    if expected and x_admin_token and x_admin_token == expected:
        return
    if request is not None:
        cookie = request.cookies.get(ADMIN_SESSION_COOKIE)
        if _is_valid_session_cookie(cookie, expected_token=expected):
            return
    raise HTTPException(status_code=401, detail="Unauthorized")


def is_admin_request_authenticated(request: Any) -> bool:
    expected = _admin_token_expected()
    headers = getattr(request, "headers", {}) or {}
    cookies = getattr(request, "cookies", {}) or {}
    header_token = str(headers.get("x-admin-token", "") or "").strip()
    if expected and header_token and header_token == expected:
        return True
    cookie = cookies.get(ADMIN_SESSION_COOKIE)
    return _is_valid_session_cookie(cookie, expected_token=expected)


def require_admin_request(request: Any) -> None:
    if is_admin_request_authenticated(request):
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/admin/session/login")
def admin_session_login(body: AdminSessionLoginRequest, response: Response):
    expected = _admin_token_expected()
    if not expected:
        raise HTTPException(status_code=503, detail="admin_token_login_unavailable")
    if not body.token or body.token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    cookie_value, expires_at = _build_session_cookie(expected_token=expected)
    max_age = max(expires_at - int(time.time()), 1)
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=cookie_value,
        max_age=max_age,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )
    return {"ok": True, "authenticated": True, "expires_at": expires_at}


@router.post("/admin/session/login-user")
async def admin_session_login_user(body: AdminUserSessionLoginRequest, response: Response):
    if _users_store is None:
        raise HTTPException(status_code=500, detail="users_store_not_configured")
    username = body.username.strip()
    password = body.password
    if not username or not password:
        raise HTTPException(status_code=400, detail="username_and_password_required")

    user = await _users_store.verify_credentials(username, password)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if str(user.get("role") or "").strip().lower() != "admin":
        raise HTTPException(status_code=403, detail="admin_role_required")

    expected = _admin_token_expected()
    cookie_value, expires_at = _build_session_cookie(expected_token=expected)
    max_age = max(expires_at - int(time.time()), 1)
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=cookie_value,
        max_age=max_age,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )
    return {
        "ok": True,
        "authenticated": True,
        "expires_at": expires_at,
        "user": {
            "username": user.get("username"),
            "role": user.get("role"),
        },
    }


@router.post("/admin/session/logout")
def admin_session_logout(response: Response):
    response.delete_cookie(key=ADMIN_SESSION_COOKIE, path="/")
    return {"ok": True, "authenticated": False}


@router.get("/admin/session/status")
def admin_session_status(request: Request):
    expected = _admin_token_expected()
    cookie = request.cookies.get(ADMIN_SESSION_COOKIE)
    return {"ok": True, "authenticated": _is_valid_session_cookie(cookie, expected_token=expected)}


@router.post("/admin/reload")
def admin_reload(request: Request, x_admin_token: str | None = Header(default=None)):
    require_admin_token(x_admin_token, request)

    # Kick the updater oneshot. This survives the backend restarting.
    try:
        subprocess.run(
            ["systemctl", "--user", "start", "synthia-updater.service"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start updater: {e.stderr or e.stdout or str(e)}",
        )

    return {"started": True, "unit": "synthia-updater.service", "log": str(LOG_FILE)}


@router.get("/admin/reload/status")
def admin_reload_status(request: Request, x_admin_token: str | None = Header(default=None)):
    require_admin_token(x_admin_token, request)

    if not LOG_FILE.exists():
        return {"exists": False, "tail": ""}

    lines = LOG_FILE.read_text(errors="ignore").splitlines()
    tail = "\n".join(lines[-200:])
    return {"exists": True, "tail": tail}
