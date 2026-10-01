from __future__ import annotations

import asyncio
import ipaddress
import os
import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.api.admin import is_admin_request_authenticated
from app.system.platform_identity import load_platform_identity


WEB_APP_API_PREFIX = "/api/web-app"
WEB_APP_CORS_METHODS = "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS"
WEB_APP_CORS_HEADERS = {"authorization", "content-type"}
WEB_APP_MAX_REQUEST_BYTES = 1024 * 1024
WEB_APP_RATE_LIMIT_WINDOW_S = 60
WEB_APP_RATE_LIMIT_DEFAULT = 120
SENSITIVE_AUTH_RATE_LIMIT_DEFAULT = 10
FORBIDDEN_CREDENTIAL_QUERY_KEYS = {"access_token", "authorization", "refresh_token", "token"}
PUBLIC_REMOTE_API_EXACT = {
    "/api/admin/session/login-user",
    "/api/admin/session/logout",
    "/api/admin/session/status",
    "/api/auth/device-enrollments",
    "/api/auth/devices",
    "/api/auth/user/login",
    "/api/auth/user/logout",
    "/api/auth/user/refresh",
    "/api/auth/user/sessions",
    "/api/auth/web-app/discovery",
}
PUBLIC_REMOTE_API_PREFIXES = (
    "/api/auth/device-enrollments/",
    "/api/auth/devices/",
    "/api/auth/user/sessions/",
    "/api/web-app/",
)


def _normalized_host(value: str) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw or "," in raw or any(ch in raw for ch in " /\\\t\r\n"):
        return None
    if raw.startswith("["):
        close = raw.find("]")
        if close < 0 or (len(raw) > close + 1 and not raw[close + 1 :].startswith(":")):
            return None
        return raw[1:close]
    if raw.count(":") > 1:
        return None
    host, separator, port = raw.partition(":")
    if not host or (separator and (not port.isdigit() or not 1 <= int(port) <= 65535)):
        return None
    return host.rstrip(".")


def _loopback_peer(request: Request) -> bool:
    host = str(getattr(request.client, "host", "") or "").strip()
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def effective_request_host(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-host")
    if forwarded and _loopback_peer(request):
        return _normalized_host(forwarded)
    return _normalized_host(request.headers.get("host", ""))


def _allowed_web_app_origins(public_hostname: str) -> set[str]:
    allowed = {f"https://{public_hostname}"}
    dev_cors = str(os.getenv("HEXE_ENABLE_DEV_CORS", "0")).strip().lower()
    if dev_cors not in {"1", "true", "yes", "on"}:
        return allowed
    configured = str(os.getenv("HEXE_CORS_ALLOW_ORIGINS", "")).strip()
    if configured:
        allowed.update(origin.strip() for origin in configured.split(",") if origin.strip())
    else:
        allowed.update({"http://localhost:5173", "http://127.0.0.1:5173"})
    return allowed


def _add_web_app_cors_headers(response: Response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Vary"] = "Origin"


def _add_public_security_headers(response: Response) -> Response:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), payment=()")
    response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'; base-uri 'self'; object-src 'none'")
    return response


def _web_app_preflight(request: Request, origin: str) -> Response:
    requested_method = str(request.headers.get("access-control-request-method") or "").upper()
    if requested_method not in {"GET", "HEAD"}:
        return JSONResponse({"detail": "cors_method_not_allowed"}, status_code=400)
    requested_headers = {
        item.strip().lower()
        for item in str(request.headers.get("access-control-request-headers") or "").split(",")
        if item.strip()
    }
    if not requested_headers.issubset(WEB_APP_CORS_HEADERS):
        return JSONResponse({"detail": "cors_headers_not_allowed"}, status_code=400)
    response = Response(status_code=204)
    _add_web_app_cors_headers(response, origin)
    response.headers["Access-Control-Allow-Methods"] = WEB_APP_CORS_METHODS
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    response.headers["Access-Control-Max-Age"] = "600"
    return response


def _public_remote_api_allowed(path: str) -> bool:
    return path in PUBLIC_REMOTE_API_EXACT or any(path.startswith(prefix) for prefix in PUBLIC_REMOTE_API_PREFIXES)


def _sensitive_public_auth_endpoint(path: str) -> bool:
    return path in {
        "/api/admin/session/login-user",
        "/api/auth/user/login",
        "/api/auth/user/refresh",
    } or (path.startswith("/api/auth/device-enrollments/") and path.endswith("/complete"))


class RemoteWebBoundaryMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        rate_limit_per_minute: int | None = None,
        sensitive_auth_rate_limit_per_minute: int | None = None,
    ) -> None:
        super().__init__(app)
        configured_limit = rate_limit_per_minute if rate_limit_per_minute is not None else WEB_APP_RATE_LIMIT_DEFAULT
        self._rate_limit = max(1, configured_limit)
        sensitive_limit = (
            sensitive_auth_rate_limit_per_minute
            if sensitive_auth_rate_limit_per_minute is not None
            else SENSITIVE_AUTH_RATE_LIMIT_DEFAULT
        )
        self._sensitive_auth_rate_limit = max(1, sensitive_limit)
        self._request_times: dict[str, deque[float]] = defaultdict(deque)
        self._rate_lock = asyncio.Lock()

    @staticmethod
    def _rate_key(request: Request) -> str:
        forwarded = str(request.headers.get("cf-connecting-ip") or "").strip()
        if forwarded and _loopback_peer(request):
            try:
                return str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
        return str(getattr(request.client, "host", "unknown") or "unknown")

    async def _rate_limited(self, request: Request, *, group: str, limit: int) -> bool:
        now = time.monotonic()
        cutoff = now - WEB_APP_RATE_LIMIT_WINDOW_S
        key = f"{group}:{self._rate_key(request)}"
        async with self._rate_lock:
            times = self._request_times[key]
            while times and times[0] <= cutoff:
                times.popleft()
            if len(times) >= limit:
                return True
            times.append(now)
            return False

    async def dispatch(self, request: Request, call_next) -> Response:
        settings_store = getattr(request.app.state, "settings_store", None)
        identity = await load_platform_identity(settings_store)
        host = effective_request_host(request)
        if host is None:
            return JSONResponse({"detail": "request_host_invalid"}, status_code=400)

        is_public = host == identity.public_hostname.lower()
        request.state.is_public_core_host = is_public

        path = request.url.path
        is_web_app_api = path == WEB_APP_API_PREFIX or path.startswith(f"{WEB_APP_API_PREFIX}/")
        origin = str(request.headers.get("origin") or "").strip()
        if is_public and path.startswith("/api/"):
            if str(request.headers.get("x-admin-token") or "").strip():
                return _add_public_security_headers(
                    JSONResponse({"detail": "remote_admin_token_forbidden"}, status_code=403)
                )
            if not _public_remote_api_allowed(path) and not is_admin_request_authenticated(request):
                return _add_public_security_headers(JSONResponse({"detail": "not_found"}, status_code=404))
            if (
                request.method != "OPTIONS"
                and _sensitive_public_auth_endpoint(path)
                and await self._rate_limited(
                    request,
                    group="sensitive-auth",
                    limit=self._sensitive_auth_rate_limit,
                )
            ):
                response = JSONResponse({"detail": "authentication_rate_limit_exceeded"}, status_code=429)
                response.headers["Retry-After"] = str(WEB_APP_RATE_LIMIT_WINDOW_S)
                return _add_public_security_headers(response)
        if is_public and is_web_app_api:
            query_keys = {str(key).strip().lower() for key in request.query_params.keys()}
            if query_keys.intersection(FORBIDDEN_CREDENTIAL_QUERY_KEYS):
                return _add_public_security_headers(
                    JSONResponse({"detail": "credentials_in_query_forbidden"}, status_code=400)
                )
            content_length = str(request.headers.get("content-length") or "").strip()
            if content_length:
                try:
                    if int(content_length) < 0:
                        raise ValueError
                except ValueError:
                    return _add_public_security_headers(
                        JSONResponse({"detail": "content_length_invalid"}, status_code=400)
                    )
                if int(content_length) > WEB_APP_MAX_REQUEST_BYTES:
                    return _add_public_security_headers(
                        JSONResponse({"detail": "request_body_too_large"}, status_code=413)
                    )
            if request.method != "OPTIONS" and await self._rate_limited(
                request,
                group="web-app",
                limit=self._rate_limit,
            ):
                response = JSONResponse({"detail": "web_app_rate_limit_exceeded"}, status_code=429)
                response.headers["Retry-After"] = str(WEB_APP_RATE_LIMIT_WINDOW_S)
                return _add_public_security_headers(response)
        if is_public and is_web_app_api and origin:
            if origin not in _allowed_web_app_origins(identity.public_hostname.lower()):
                return _add_public_security_headers(
                    JSONResponse({"detail": "cors_origin_not_allowed"}, status_code=403)
                )
            if request.method == "OPTIONS":
                return _add_public_security_headers(_web_app_preflight(request, origin))
        if is_public and request.method in {"GET", "HEAD"} and path == "/":
            query = str(request.url.query or "")
            target = "/app" + (f"?{query}" if query else "")
            return _add_public_security_headers(RedirectResponse(target, status_code=307))
        if path == "/remote" or path.startswith("/remote/"):
            response = JSONResponse({"detail": "not_found"}, status_code=404)
            return _add_public_security_headers(response) if is_public else response

        response = await call_next(request)
        if is_public:
            _add_public_security_headers(response)
            if is_web_app_api and origin:
                _add_web_app_cors_headers(response, origin)
        return response
