from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from html import escape
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket

from app.api.admin import admin_request_actor, require_admin_request
from app.reverse_proxy import ReverseProxyService
from app.system.management_access import NODE_MANAGEMENT_PERMISSIONS, ManagementAuthorizationService
from app.system.audit import AuditLogStore
from app.system.onboarding import NodeRegistrationsStore, NodeTrustIssuanceService
from app.system.users import UsersStore
from app.ui_target_resolver import UiTargetResolver
from .service import NodesDomainService

log = logging.getLogger("hexe.proxy")
HTML_ROOT_URL_ATTR_RE = re.compile(r'(?P<prefix>\b(?:src|href|action)=["\'])(?P<path>/[^"\']*)')
ROOT_URL_STRING_RE = re.compile(r'(?P<quote>["\'`])(?P<path>/[^"\'`]*)(?P=quote)')
PROXIED_NODE_PATH_DETECTOR = r"/^\/nodes\/([^/]+)\/ui(?:\/.*)?$/i"
PROXIED_NODE_PATH_DETECTOR_REWRITE = r"/^\/nodes\/proxy\/([^/]+)(?:\/.*)?$/i"
CANONICAL_PROXIED_NODE_PATH_DETECTOR = r"/^\/nodes\/proxy\/ui\/([^/]+)(?:\/.*)?$/i"


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, str(default)).strip()))
    except Exception:
        return default


NODE_PROXY_TIMEOUT_SECONDS = 10.0
NODE_UI_HEALTH_TIMEOUT_SECONDS = 2.0


def _admin_login_redirect(request: Request) -> Response:
    next_target = str(request.url.path or "").strip() or "/"
    if request.url.query:
        next_target = f"{next_target}?{request.url.query}"
    return Response(
        status_code=307,
        headers={"location": f"/proxy-login?next={quote(next_target, safe='')}"},
    )


def _reserved_node_proxy_segment(node_id: str) -> bool:
    return str(node_id or "").strip() in {"ui", "no-json"}


def _public_node_oauth_callback_path(path: str) -> bool:
    normalized = str(path or "").strip("/")
    return normalized in {"google/callback", "google/gmail/callback"}


class NodeUiProxy:
    def __init__(
        self,
        service: NodesDomainService,
        *,
        management_authorization: ManagementAuthorizationService | None = None,
        node_trust: NodeTrustIssuanceService | None = None,
        registrations: NodeRegistrationsStore | None = None,
        users: UsersStore | None = None,
        audit: AuditLogStore | None = None,
    ) -> None:
        self._service = service
        self._targets = UiTargetResolver(nodes_service=service)
        self._proxy = ReverseProxyService(
            client=httpx.AsyncClient(
                follow_redirects=False,
                timeout=httpx.Timeout(_env_float("HEXE_NODE_PROXY_TIMEOUT_SECONDS", NODE_PROXY_TIMEOUT_SECONDS)),
            )
        )
        self._management_authorization = management_authorization
        self._node_trust = node_trust
        self._registrations = registrations
        self._users = users
        self._audit = audit
        self._management_cache: dict[tuple[str, str], tuple[str, int, str]] = {}
        self._management_cache_locks: dict[tuple[str, str], asyncio.Lock] = {}

    def _invalidate_management_cache(self, request: Request | WebSocket, node_id: str) -> None:
        try:
            actor_id, _ = admin_request_actor(request)
        except HTTPException:
            return
        self._management_cache.pop((actor_id, node_id), None)

    async def _management_headers(self, request: Request | WebSocket, node_id: str) -> dict[str, str]:
        if self._management_authorization is None:
            return {}
        actor_id, actor_role = admin_request_actor(request)
        if actor_id not in {"admin_token", "legacy_admin_session"}:
            user = await self._users.get_user(actor_id) if self._users is not None else None
            if user is None or not bool(user.get("enabled")) or str(user.get("role")) not in {"owner", "admin"}:
                raise HTTPException(status_code=403, detail="operator_access_revoked")
        registration = self._registrations.get(node_id) if self._registrations is not None else None
        trusted = self._node_trust.trusted_node(node_id) if self._node_trust is not None else None
        if registration is None:
            raise HTTPException(status_code=404, detail="management_target_node_not_found")
        if str(registration.trust_status or "").lower() != "trusted" or trusted is None:
            raise HTTPException(status_code=409, detail="management_target_node_untrusted")
        cache_key = (actor_id, node_id)
        lock = self._management_cache_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = self._management_cache.get(cache_key)
            cached_authorization = self._management_authorization.store.get(cached[2]) if cached is not None else None
            if cached is not None and cached[1] > int(time.time()) + 30 and cached_authorization is not None and cached_authorization.active():
                return {"X-Hexe-Management-Authorization": cached[0]}
            token, claims = await self._management_authorization.issue(
                operator_id=actor_id,
                operator_role=actor_role,
                target_node_id=node_id,
                scopes=sorted(NODE_MANAGEMENT_PERMISSIONS),
            )
            self._management_cache[cache_key] = (token, int(claims["exp"]), str(claims["authorization_id"]))
        if self._audit is not None:
            await self._audit.record(
                event_type="node_management_proxy_authorized",
                actor_role=actor_role,
                actor_id=actor_id,
                details={
                    "authorization_id": claims["authorization_id"],
                    "target_node_id": node_id,
                    "scopes": claims["scp"],
                    "jti": claims["jti"],
                },
            )
        return {"X-Hexe-Management-Authorization": token}

    async def aclose(self) -> None:
        await self._proxy.aclose()

    def _target_base(self, node_id: str, request: Request) -> str:
        return self._targets.resolve_node_ui(node_id).target_base

    def _api_target_base(self, node_id: str, request: Request) -> str:
        return self._targets.resolve_node_api(node_id).target_base

    def _api_root_target_base(self, node_id: str, request: Request) -> str:
        parsed = urlsplit(self._api_target_base(node_id, request))
        return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))

    @staticmethod
    def _log_proxy_result(
        *,
        node_id: str,
        surface: str,
        method: str,
        path: str,
        public_prefix: str,
        status_code: int,
        latency_ms: float,
        outcome: str,
    ) -> None:
        log.info(
            "proxy node surface=%s node_id=%s method=%s path=%s prefix=%s status=%s latency_ms=%.1f outcome=%s",
            surface,
            node_id,
            method,
            path or "/",
            public_prefix,
            status_code,
            latency_ms,
            outcome,
        )

    async def _ui_health_state(self, node_id: str) -> tuple[bool, str | None]:
        raw_endpoint = self._targets.resolve_node_ui(node_id).health_endpoint
        if not raw_endpoint:
            return True, None
        return await self._proxy.probe_health(
            raw_endpoint,
            timeout=httpx.Timeout(_env_float("HEXE_NODE_UI_HEALTH_TIMEOUT_SECONDS", NODE_UI_HEALTH_TIMEOUT_SECONDS)),
        )

    async def forward(
        self,
        request: Request,
        node_id: str,
        path: str = "",
        *,
        public_prefix: str = "",
        render_navigation_json_page: bool = False,
        api_public_prefix: str | None = None,
    ) -> Response:
        started_at = time.perf_counter()
        effective_public_prefix = public_prefix or f"/nodes/proxy/{node_id}"
        try:
            resolved_target = self._targets.resolve_node_ui(node_id)
            target_base = resolved_target.target_base
        except HTTPException as exc:
            self._log_proxy_result(
                node_id=node_id,
                surface="ui",
                method=request.method,
                path=path,
                public_prefix=effective_public_prefix,
                status_code=exc.status_code,
                latency_ms=(time.perf_counter() - started_at) * 1000.0,
                outcome=str(exc.detail),
            )
            return self._proxy.build_ui_error_response(
                status_code=exc.status_code,
                detail=str(exc.detail),
                title="Node UI Unavailable",
                target_label=node_id,
                public_prefix=effective_public_prefix,
            )
        healthy, health_detail = await self._ui_health_state(node_id)
        if not healthy:
            self._log_proxy_result(
                node_id=node_id,
                surface="ui",
                method=request.method,
                path=path,
                public_prefix=effective_public_prefix,
                status_code=503,
                latency_ms=(time.perf_counter() - started_at) * 1000.0,
                outcome=str(health_detail or "node_unhealthy"),
            )
            return self._proxy.build_ui_error_response(
                status_code=503,
                detail=str(health_detail or "node_unhealthy"),
                title="Node UI Unavailable",
                target_label=node_id,
                public_prefix=effective_public_prefix,
            )
        target = self._proxy.build_target_url(target_base, path, request.url.query)
        headers = self._proxy.build_request_headers(
            request,
            public_prefix=effective_public_prefix,
            extra_headers={"X-Hexe-Node-Id": node_id, **await self._management_headers(request, node_id)},
        )
        # UI bodies can be rewritten below, so upstream validators do not
        # describe the bytes held by the browser at the public proxy URL.
        for header_name in tuple(headers):
            if header_name.lower() in {"if-none-match", "if-modified-since"}:
                headers.pop(header_name, None)
        try:
            upstream = await self._proxy.send(
                request=request,
                target_url=target,
                headers=headers,
            )
        except HTTPException as exc:
            if exc.status_code == 502:
                self._log_proxy_result(
                    node_id=node_id,
                    surface="ui",
                    method=request.method,
                    path=path,
                    public_prefix=effective_public_prefix,
                    status_code=502,
                    latency_ms=(time.perf_counter() - started_at) * 1000.0,
                    outcome=f"node_ui_proxy_error: {str(exc.detail).removeprefix('proxy_error: ')}",
                )
                return self._proxy.build_ui_error_response(
                    status_code=502,
                    detail=f"node_ui_proxy_error: {str(exc.detail).removeprefix('proxy_error: ')}",
                    title="Node UI Unavailable",
                    target_label=node_id,
                    public_prefix=effective_public_prefix,
                )
            self._log_proxy_result(
                node_id=node_id,
                surface="ui",
                method=request.method,
                path=path,
                public_prefix=effective_public_prefix,
                status_code=exc.status_code,
                latency_ms=(time.perf_counter() - started_at) * 1000.0,
                outcome=str(exc.detail),
            )
            return self._proxy.build_ui_error_response(
                status_code=exc.status_code,
                detail=str(exc.detail),
                title="Node UI Unavailable",
                target_label=node_id,
                public_prefix=effective_public_prefix,
            )
        try:
            content = await upstream.aread()
        except httpx.HTTPError as exc:
            await upstream.aclose()
            self._log_proxy_result(
                node_id=node_id,
                surface="ui",
                method=request.method,
                path=path,
                public_prefix=effective_public_prefix,
                status_code=502,
                latency_ms=(time.perf_counter() - started_at) * 1000.0,
                outcome=f"node_ui_proxy_read_error: {type(exc).__name__}",
            )
            return self._proxy.build_ui_error_response(
                status_code=502,
                detail=f"node_ui_proxy_read_error: {type(exc).__name__}",
                title="Node UI Unavailable",
                target_label=node_id,
                public_prefix=effective_public_prefix,
            )
        if upstream.status_code == 401:
            self._invalidate_management_cache(request, node_id)
        response_headers = self._proxy.decoded_response_headers(upstream.headers)
        response_headers.pop("etag", None)
        response_headers.pop("last-modified", None)
        await upstream.aclose()
        if render_navigation_json_page:
            callback_page = self._render_browser_json_navigation_page(
                request=request,
                status_code=upstream.status_code,
                content=content,
                content_type=response_headers.get("content-type"),
            )
            if callback_page is not None:
                response_headers["content-type"] = "text/html; charset=utf-8"
                response_headers.pop("content-length", None)
                content = callback_page
        content = self._rewrite_root_urls(
            content,
            response_headers.get("content-type"),
            public_prefix=effective_public_prefix,
            api_public_prefix=api_public_prefix or f"/api/nodes/{node_id}",
        )
        self._log_proxy_result(
            node_id=node_id,
            surface="ui",
            method=request.method,
            path=path,
            public_prefix=effective_public_prefix,
            status_code=upstream.status_code,
            latency_ms=(time.perf_counter() - started_at) * 1000.0,
            outcome="proxied",
        )
        return Response(
            content=content,
            status_code=upstream.status_code,
            headers=response_headers,
        )

    @staticmethod
    def _render_browser_json_navigation_page(
        *,
        request: Request,
        status_code: int,
        content: bytes,
        content_type: str | None,
    ) -> bytes | None:
        normalized_type = str(content_type or "").lower()
        accept = str(request.headers.get("accept", "") or "").lower()
        if "json" not in normalized_type or "text/html" not in accept:
            return None
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

        if 200 <= status_code < 300:
            title = "Request Complete"
            message = "The proxied node request completed successfully. This window can close now."
            should_close = True
        else:
            detail = payload.get("detail") if isinstance(payload, dict) else None
            title = "Request Failed"
            message = str(detail or "The proxied node request did not complete successfully.")
            should_close = False
        return NodeUiProxy._build_oauth_callback_html(title=title, message=message, should_close=should_close)

    @staticmethod
    def _build_oauth_callback_html(*, title: str, message: str, should_close: bool) -> bytes:
        safe_title = escape(title)
        safe_message = escape(message)
        auto_close = """
        <script>
        (function () {
          try {
            if (window.opener && !window.opener.closed) {
              window.opener.postMessage({ type: "hexe:gmail-oauth-complete" }, "*");
            }
          } catch (error) {}
          window.close();
        })();
        </script>
        """ if should_close else ""
        html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{safe_title}</title>
    <style>
      :root {{
        color-scheme: light;
        font-family: ui-sans-serif, system-ui, sans-serif;
        background: #f4efe7;
        color: #1f2933;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background:
          radial-gradient(circle at top, rgba(216, 173, 120, 0.25), transparent 40%),
          linear-gradient(180deg, #f7f2eb 0%, #efe5d6 100%);
      }}
      main {{
        width: min(28rem, calc(100vw - 2rem));
        padding: 2rem;
        border-radius: 1.25rem;
        background: rgba(255, 252, 247, 0.92);
        box-shadow: 0 24px 70px rgba(78, 52, 24, 0.16);
      }}
      h1 {{
        margin: 0 0 0.75rem;
        font-size: 1.4rem;
      }}
      p {{
        margin: 0;
        line-height: 1.5;
      }}
    </style>
    {auto_close}
  </head>
  <body>
    <main>
      <h1>{safe_title}</h1>
      <p>{safe_message}</p>
    </main>
  </body>
</html>
"""
        return html.encode("utf-8")

    @staticmethod
    def _rewrite_root_urls(
        content: bytes,
        content_type: str | None,
        *,
        public_prefix: str,
        api_public_prefix: str,
    ) -> bytes:
        normalized_type = str(content_type or "").lower()
        is_html = "text/html" in normalized_type
        is_js = "javascript" in normalized_type
        is_css = "text/css" in normalized_type
        if not (is_html or is_js or is_css):
            return content
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return content

        normalized_ui_prefix = public_prefix.rstrip("/")
        normalized_api_prefix = api_public_prefix.rstrip("/")
        ignore_prefixes = ("/nodes/proxy/", "/nodes/", "/ui/nodes/", "/api/nodes/")
        proxy_aware_javascript = is_js and CANONICAL_PROXIED_NODE_PATH_DETECTOR in text

        def should_rewrite(path: str) -> bool:
            if not path.startswith("/") or path == "/":
                return False
            for prefix in ignore_prefixes:
                normalized = str(prefix or "").rstrip("/")
                if normalized and (path == normalized or path.startswith(f"{normalized}/")):
                    return False
            return True

        def rewrite_attr_path(path: str) -> str:
            if not should_rewrite(path):
                return path
            if path == "/api":
                return normalized_api_prefix
            if path.startswith("/api/"):
                return f"{normalized_api_prefix}{path.removeprefix('/api')}"
            return f"{normalized_ui_prefix}{path}"

        def rewrite_string_path(path: str) -> str:
            if not should_rewrite(path):
                return path
            if proxy_aware_javascript and (path == "/api" or path.startswith("/api/")):
                return path
            if path == "/api":
                return normalized_api_prefix
            if path.startswith("/api/"):
                return f"{normalized_api_prefix}{path.removeprefix('/api')}"
            return f"{normalized_ui_prefix}{path}"

        rewritten = text
        if is_html:
            rewritten = HTML_ROOT_URL_ATTR_RE.sub(
                lambda match: f"{match.group('prefix')}{rewrite_attr_path(match.group('path'))}",
                rewritten,
            )
        rewritten = ROOT_URL_STRING_RE.sub(
            lambda match: f"{match.group('quote')}{rewrite_string_path(match.group('path'))}{match.group('quote')}",
            rewritten,
        )
        if is_js:
            rewritten = rewritten.replace(PROXIED_NODE_PATH_DETECTOR, PROXIED_NODE_PATH_DETECTOR_REWRITE)
        return rewritten.encode("utf-8")

    async def forward_websocket(self, websocket: WebSocket, node_id: str, path: str = "", *, public_prefix: str = "") -> None:
        started_at = time.perf_counter()
        healthy, health_detail = await self._ui_health_state(node_id)
        if not healthy:
            self._log_proxy_result(
                node_id=node_id,
                surface="ui_ws",
                method="WS",
                path=path,
                public_prefix=public_prefix or f"/nodes/proxy/{node_id}",
                status_code=1013,
                latency_ms=(time.perf_counter() - started_at) * 1000.0,
                outcome=str(health_detail or "node_unhealthy"),
            )
            await websocket.close(code=1013, reason=str(health_detail or "node_unhealthy"))
            return
        target_base = self._target_base(node_id, websocket)
        target = self._proxy.build_websocket_target_url(target_base, path, websocket.url.query)
        try:
            management_headers = await self._management_headers(websocket, node_id)
        except HTTPException as exc:
            await websocket.close(code=4403 if exc.status_code != 401 else 4401, reason=str(exc.detail))
            return
        await self._proxy.proxy_websocket(
            websocket,
            target_url=target,
                public_prefix=public_prefix or f"/nodes/proxy/{node_id}",
            extra_headers={"X-Hexe-Node-Id": node_id, **management_headers},
        )
        self._log_proxy_result(
            node_id=node_id,
            surface="ui_ws",
            method="WS",
            path=path,
            public_prefix=public_prefix or f"/nodes/proxy/{node_id}",
            status_code=101,
            latency_ms=(time.perf_counter() - started_at) * 1000.0,
            outcome="proxied",
        )

    async def forward_api(
        self,
        request: Request,
        node_id: str,
        path: str = "",
        *,
        public_prefix: str | None = None,
        render_navigation_json_page: bool = False,
    ) -> Response:
        started_at = time.perf_counter()
        target_base = (
            self._api_root_target_base(node_id, request)
            if _public_node_oauth_callback_path(path)
            else self._api_target_base(node_id, request)
        )
        target = self._proxy.build_target_url(target_base, path, request.url.query)
        effective_public_prefix = public_prefix or f"/api/nodes/{node_id}"
        headers = self._proxy.build_request_headers(
            request,
            public_prefix=effective_public_prefix,
            extra_headers={
                "X-Hexe-Node-Id": node_id,
                **({} if _public_node_oauth_callback_path(path) else await self._management_headers(request, node_id)),
            },
        )
        try:
            upstream = await self._proxy.send(
                request=request,
                target_url=target,
                headers=headers,
            )
        except HTTPException as exc:
            if exc.status_code == 502:
                self._log_proxy_result(
                    node_id=node_id,
                    surface="api",
                    method=request.method,
                    path=path,
                    public_prefix=effective_public_prefix,
                    status_code=502,
                    latency_ms=(time.perf_counter() - started_at) * 1000.0,
                    outcome=f"node_api_proxy_error: {str(exc.detail).removeprefix('proxy_error: ')}",
                )
                raise HTTPException(status_code=502, detail=f"node_api_proxy_error: {str(exc.detail).removeprefix('proxy_error: ')}")
            raise
        self._log_proxy_result(
            node_id=node_id,
            surface="api",
            method=request.method,
            path=path,
            public_prefix=effective_public_prefix,
            status_code=upstream.status_code,
            latency_ms=(time.perf_counter() - started_at) * 1000.0,
            outcome="proxied",
        )
        if upstream.status_code == 401:
            self._invalidate_management_cache(request, node_id)
        if not render_navigation_json_page:
            return await self._proxy.stream_response(upstream)

        content = await upstream.aread()
        response_headers = self._proxy.decoded_response_headers(upstream.headers)
        await upstream.aclose()
        callback_page = self._render_browser_json_navigation_page(
            request=request,
            status_code=upstream.status_code,
            content=content,
            content_type=response_headers.get("content-type"),
        )
        if callback_page is not None:
            response_headers["content-type"] = "text/html; charset=utf-8"
            response_headers.pop("content-length", None)
            content = callback_page
        return Response(
            content=content,
            status_code=upstream.status_code,
            headers=response_headers,
        )


def build_node_ui_proxy_router(proxy: NodeUiProxy) -> APIRouter:
    router = APIRouter(include_in_schema=False)

    @router.api_route("/nodes/proxy/ui/{node_id}/{path:path}", methods=["GET", "HEAD"])
    async def proxy_node_ui_navigation(node_id: str, path: str, request: Request):
        try:
            require_admin_request(request)
        except HTTPException as exc:
            if exc.status_code == 401:
                return _admin_login_redirect(request)
            raise
        return await proxy.forward(
            request,
            node_id,
            path,
            public_prefix=f"/nodes/proxy/ui/{node_id}",
            api_public_prefix=f"/nodes/proxy/{node_id}",
        )

    @router.api_route("/nodes/proxy/ui/{node_id}/", methods=["GET", "HEAD"])
    async def proxy_node_ui_navigation_root(node_id: str, request: Request):
        try:
            require_admin_request(request)
        except HTTPException as exc:
            if exc.status_code == 401:
                return _admin_login_redirect(request)
            raise
        return await proxy.forward(
            request,
            node_id,
            "",
            public_prefix=f"/nodes/proxy/ui/{node_id}",
            api_public_prefix=f"/nodes/proxy/{node_id}",
        )

    @router.api_route("/nodes/proxy/ui/{node_id}", methods=["GET", "HEAD"])
    async def proxy_node_ui_navigation_root_no_slash(node_id: str, request: Request):
        try:
            require_admin_request(request)
        except HTTPException as exc:
            if exc.status_code == 401:
                return _admin_login_redirect(request)
            raise
        return await proxy.forward(
            request,
            node_id,
            "",
            public_prefix=f"/nodes/proxy/ui/{node_id}",
            api_public_prefix=f"/nodes/proxy/{node_id}",
        )

    @router.api_route(
        "/nodes/proxy/no-json/{node_id}/{path:path}",
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    async def proxy_node_api_navigation(node_id: str, path: str, request: Request):
        if not (request.method in {"GET", "HEAD"} and _public_node_oauth_callback_path(path)):
            try:
                require_admin_request(request)
            except HTTPException as exc:
                if exc.status_code == 401 and request.method in {"GET", "HEAD"}:
                    return _admin_login_redirect(request)
                raise
        return await proxy.forward_api(
            request,
            node_id,
            path,
            public_prefix=f"/nodes/proxy/no-json/{node_id}",
            render_navigation_json_page=True,
        )

    @router.api_route(
        "/nodes/proxy/no-json/{node_id}/",
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    async def proxy_node_api_navigation_root(node_id: str, request: Request):
        try:
            require_admin_request(request)
        except HTTPException as exc:
            if exc.status_code == 401 and request.method in {"GET", "HEAD"}:
                return _admin_login_redirect(request)
            raise
        return await proxy.forward_api(
            request,
            node_id,
            "",
            public_prefix=f"/nodes/proxy/no-json/{node_id}",
            render_navigation_json_page=True,
        )

    @router.api_route(
        "/nodes/proxy/no-json/{node_id}",
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    async def proxy_node_api_navigation_root_no_slash(node_id: str, request: Request):
        try:
            require_admin_request(request)
        except HTTPException as exc:
            if exc.status_code == 401 and request.method in {"GET", "HEAD"}:
                return _admin_login_redirect(request)
            raise
        return await proxy.forward_api(
            request,
            node_id,
            "",
            public_prefix=f"/nodes/proxy/no-json/{node_id}",
            render_navigation_json_page=True,
        )

    @router.api_route(
        "/nodes/proxy/{node_id}/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def proxy_node_api_canonical(node_id: str, path: str, request: Request):
        if _reserved_node_proxy_segment(node_id):
            raise HTTPException(status_code=405, detail="Method Not Allowed")
        try:
            require_admin_request(request)
        except HTTPException as exc:
            if exc.status_code == 401 and request.method in {"GET", "HEAD"}:
                return _admin_login_redirect(request)
            raise
        return await proxy.forward_api(request, node_id, path, public_prefix=f"/nodes/proxy/{node_id}")

    @router.api_route(
        "/nodes/proxy/{node_id}/",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def proxy_node_api_canonical_root(node_id: str, request: Request):
        if _reserved_node_proxy_segment(node_id):
            raise HTTPException(status_code=405, detail="Method Not Allowed")
        try:
            require_admin_request(request)
        except HTTPException as exc:
            if exc.status_code == 401 and request.method in {"GET", "HEAD"}:
                return _admin_login_redirect(request)
            raise
        return await proxy.forward_api(request, node_id, "", public_prefix=f"/nodes/proxy/{node_id}")

    @router.api_route(
        "/nodes/proxy/{node_id}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def proxy_node_api_canonical_root_no_slash(node_id: str, request: Request):
        if _reserved_node_proxy_segment(node_id):
            raise HTTPException(status_code=405, detail="Method Not Allowed")
        try:
            require_admin_request(request)
        except HTTPException as exc:
            if exc.status_code == 401 and request.method in {"GET", "HEAD"}:
                return _admin_login_redirect(request)
            raise
        return await proxy.forward_api(request, node_id, "", public_prefix=f"/nodes/proxy/{node_id}")

    @router.api_route("/nodes/{node_id}/ui/{path:path}", methods=["GET", "HEAD"])
    async def proxy_node_ui_legacy_canonical(node_id: str, path: str, request: Request):
        try:
            require_admin_request(request)
        except HTTPException as exc:
            if exc.status_code == 401:
                return _admin_login_redirect(request)
            raise
        return await proxy.forward(request, node_id, path, public_prefix=f"/nodes/{node_id}/ui")

    @router.api_route("/nodes/{node_id}/ui/", methods=["GET", "HEAD"])
    async def proxy_node_ui_legacy_canonical_root(node_id: str, request: Request):
        try:
            require_admin_request(request)
        except HTTPException as exc:
            if exc.status_code == 401:
                return _admin_login_redirect(request)
            raise
        return await proxy.forward(request, node_id, "", public_prefix=f"/nodes/{node_id}/ui")

    @router.api_route("/nodes/{node_id}/ui", methods=["GET", "HEAD"])
    async def proxy_node_ui_legacy_canonical_root_no_slash(node_id: str, request: Request):
        try:
            require_admin_request(request)
        except HTTPException as exc:
            if exc.status_code == 401:
                return _admin_login_redirect(request)
            raise
        return await proxy.forward(request, node_id, "", public_prefix=f"/nodes/{node_id}/ui")

    @router.api_route("/ui/nodes/{node_id}/{path:path}", methods=["GET", "HEAD"])
    async def proxy_node_ui(node_id: str, path: str, request: Request):
        try:
            require_admin_request(request)
        except HTTPException as exc:
            if exc.status_code == 401:
                return _admin_login_redirect(request)
            raise
        return await proxy.forward(request, node_id, path, public_prefix=f"/ui/nodes/{node_id}")

    @router.api_route("/ui/nodes/{node_id}", methods=["GET", "HEAD"])
    async def proxy_node_ui_root(node_id: str, request: Request):
        try:
            require_admin_request(request)
        except HTTPException as exc:
            if exc.status_code == 401:
                return _admin_login_redirect(request)
            raise
        return await proxy.forward(request, node_id, "", public_prefix=f"/ui/nodes/{node_id}")

    @router.api_route(
        "/api/nodes/{node_id}/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def proxy_node_api(node_id: str, path: str, request: Request):
        require_admin_request(request)
        return await proxy.forward_api(request, node_id, path)

    @router.api_route(
        "/api/nodes/{node_id}/",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def proxy_node_api_root(node_id: str, request: Request):
        require_admin_request(request)
        return await proxy.forward_api(request, node_id, "")

    @router.websocket("/nodes/proxy/ui/{node_id}/{path:path}")
    async def proxy_node_ui_navigation_websocket(node_id: str, path: str, websocket: WebSocket):
        try:
            require_admin_request(websocket)
        except HTTPException:
            await websocket.close(code=4401, reason="Unauthorized")
            return
        await proxy.forward_websocket(websocket, node_id, path, public_prefix=f"/nodes/proxy/ui/{node_id}")

    @router.websocket("/nodes/proxy/ui/{node_id}/")
    async def proxy_node_ui_navigation_root_websocket(node_id: str, websocket: WebSocket):
        try:
            require_admin_request(websocket)
        except HTTPException:
            await websocket.close(code=4401, reason="Unauthorized")
            return
        await proxy.forward_websocket(websocket, node_id, "", public_prefix=f"/nodes/proxy/ui/{node_id}")

    @router.websocket("/nodes/proxy/{node_id}/{path:path}")
    async def proxy_node_ui_canonical_websocket(node_id: str, path: str, websocket: WebSocket):
        try:
            require_admin_request(websocket)
        except HTTPException:
            await websocket.close(code=4401, reason="Unauthorized")
            return
        await proxy.forward_websocket(websocket, node_id, path, public_prefix=f"/nodes/proxy/{node_id}")

    @router.websocket("/nodes/proxy/{node_id}/")
    async def proxy_node_ui_canonical_root_websocket(node_id: str, websocket: WebSocket):
        try:
            require_admin_request(websocket)
        except HTTPException:
            await websocket.close(code=4401, reason="Unauthorized")
            return
        await proxy.forward_websocket(websocket, node_id, "", public_prefix=f"/nodes/proxy/{node_id}")

    @router.websocket("/nodes/{node_id}/ui/{path:path}")
    async def proxy_node_ui_legacy_canonical_websocket(node_id: str, path: str, websocket: WebSocket):
        try:
            require_admin_request(websocket)
        except HTTPException:
            await websocket.close(code=4401, reason="Unauthorized")
            return
        await proxy.forward_websocket(websocket, node_id, path, public_prefix=f"/nodes/{node_id}/ui")

    @router.websocket("/nodes/{node_id}/ui/")
    async def proxy_node_ui_legacy_canonical_root_websocket(node_id: str, websocket: WebSocket):
        try:
            require_admin_request(websocket)
        except HTTPException:
            await websocket.close(code=4401, reason="Unauthorized")
            return
        await proxy.forward_websocket(websocket, node_id, "", public_prefix=f"/nodes/{node_id}/ui")

    @router.websocket("/ui/nodes/{node_id}/{path:path}")
    async def proxy_node_ui_websocket(node_id: str, path: str, websocket: WebSocket):
        try:
            require_admin_request(websocket)
        except HTTPException:
            await websocket.close(code=4401, reason="Unauthorized")
            return
        await proxy.forward_websocket(websocket, node_id, path, public_prefix=f"/ui/nodes/{node_id}")

    @router.websocket("/ui/nodes/{node_id}")
    async def proxy_node_ui_root_websocket(node_id: str, websocket: WebSocket):
        try:
            require_admin_request(websocket)
        except HTTPException:
            await websocket.close(code=4401, reason="Unauthorized")
            return
        await proxy.forward_websocket(websocket, node_id, "", public_prefix=f"/ui/nodes/{node_id}")

    return router
