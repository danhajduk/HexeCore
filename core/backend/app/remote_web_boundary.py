from __future__ import annotations

import ipaddress
import os

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.system.platform_identity import load_platform_identity


WEB_APP_API_PREFIX = "/api/web-app"
WEB_APP_CORS_METHODS = "GET, HEAD, OPTIONS"
WEB_APP_CORS_HEADERS = {"authorization", "content-type"}


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


class RemoteWebBoundaryMiddleware(BaseHTTPMiddleware):
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
        if is_public and is_web_app_api and origin:
            if origin not in _allowed_web_app_origins(identity.public_hostname.lower()):
                return JSONResponse({"detail": "cors_origin_not_allowed"}, status_code=403)
            if request.method == "OPTIONS":
                return _web_app_preflight(request, origin)
        if is_public and request.method in {"GET", "HEAD"} and path == "/":
            query = str(request.url.query or "")
            target = "/app" + (f"?{query}" if query else "")
            return RedirectResponse(target, status_code=307)
        if path == "/remote" or path.startswith("/remote/"):
            return JSONResponse({"detail": "not_found"}, status_code=404)

        response = await call_next(request)
        if is_public:
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "same-origin")
            response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), payment=()")
            response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'; base-uri 'self'; object-src 'none'")
            if is_web_app_api and origin:
                _add_web_app_cors_headers(response, origin)
        return response
