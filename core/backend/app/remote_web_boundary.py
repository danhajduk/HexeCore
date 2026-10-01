from __future__ import annotations

import ipaddress

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.system.platform_identity import load_platform_identity


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
        return response
