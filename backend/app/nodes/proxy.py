from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket

from app.reverse_proxy import ReverseProxyService
from .service import NodesDomainService


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, str(default)).strip()))
    except Exception:
        return default


NODE_PROXY_TIMEOUT_SECONDS = 10.0


class NodeUiProxy:
    def __init__(self, service: NodesDomainService) -> None:
        self._service = service
        self._proxy = ReverseProxyService(
            client=httpx.AsyncClient(
                follow_redirects=False,
                timeout=httpx.Timeout(_env_float("SYNTHIA_NODE_PROXY_TIMEOUT_SECONDS", NODE_PROXY_TIMEOUT_SECONDS)),
            )
        )

    async def aclose(self) -> None:
        await self._proxy.aclose()

    def _target_base(self, node_id: str, request: Request) -> str:
        node = self._service.get_node(node_id)
        if not bool(getattr(node, "ui_enabled", False)):
            raise HTTPException(status_code=404, detail="node_ui_not_enabled")
        raw_endpoint = str(getattr(node, "ui_base_url", "") or "").strip()
        if raw_endpoint:
            parsed = urlsplit(raw_endpoint)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return raw_endpoint.rstrip("/")
            raise HTTPException(status_code=502, detail="node_ui_endpoint_invalid")
        raise HTTPException(status_code=404, detail="node_ui_endpoint_not_configured")

    def _api_target_base(self, node_id: str, request: Request) -> str:
        ui_base = self._target_base(node_id, request)
        parsed = urlsplit(ui_base)
        return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))

    async def forward(self, request: Request, node_id: str, path: str = "", *, public_prefix: str = "") -> Response:
        effective_public_prefix = public_prefix or f"/nodes/{node_id}/ui"
        try:
            target_base = self._target_base(node_id, request)
        except HTTPException as exc:
            return self._proxy.build_ui_error_response(
                status_code=exc.status_code,
                detail=str(exc.detail),
                title="Node UI Unavailable",
                target_label=node_id,
                public_prefix=effective_public_prefix,
            )
        target = self._proxy.build_target_url(target_base, path, request.url.query)
        headers = self._proxy.build_request_headers(
            request,
            public_prefix=effective_public_prefix,
            extra_headers={"X-Hexe-Node-Id": node_id},
        )
        try:
            upstream = await self._proxy.send(
                request=request,
                target_url=target,
                headers=headers,
            )
        except HTTPException as exc:
            if exc.status_code == 502:
                return self._proxy.build_ui_error_response(
                    status_code=502,
                    detail=f"node_ui_proxy_error: {str(exc.detail).removeprefix('proxy_error: ')}",
                    title="Node UI Unavailable",
                    target_label=node_id,
                    public_prefix=effective_public_prefix,
                )
            return self._proxy.build_ui_error_response(
                status_code=exc.status_code,
                detail=str(exc.detail),
                title="Node UI Unavailable",
                target_label=node_id,
                public_prefix=effective_public_prefix,
            )
        content = await upstream.aread()
        response_headers = self._proxy.safe_response_headers(upstream.headers)
        await upstream.aclose()
        content = self._rewrite_root_urls(
            content,
            response_headers.get("content-type"),
            public_prefix=effective_public_prefix,
        )
        return Response(
            content=content,
            status_code=upstream.status_code,
            headers=response_headers,
        )

    @staticmethod
    def _rewrite_root_urls(content: bytes, content_type: str | None, *, public_prefix: str) -> bytes:
        return ReverseProxyService.rewrite_root_relative_urls(
            content,
            content_type,
            proxy_prefix=public_prefix,
            ignore_prefixes=("/nodes/", "/ui/nodes/"),
        )

    async def forward_websocket(self, websocket: WebSocket, node_id: str, path: str = "", *, public_prefix: str = "") -> None:
        target_base = self._target_base(node_id, websocket)
        target = self._proxy.build_websocket_target_url(target_base, path, websocket.url.query)
        await self._proxy.proxy_websocket(
            websocket,
            target_url=target,
            public_prefix=public_prefix or f"/nodes/{node_id}/ui",
            extra_headers={"X-Hexe-Node-Id": node_id},
        )

    async def forward_api(self, request: Request, node_id: str, path: str = "") -> Response:
        target_base = self._api_target_base(node_id, request)
        target = self._proxy.build_target_url(target_base, path, request.url.query)
        headers = self._proxy.build_request_headers(
            request,
            public_prefix=f"/api/nodes/{node_id}",
            extra_headers={"X-Hexe-Node-Id": node_id},
        )
        try:
            upstream = await self._proxy.send(
                request=request,
                target_url=target,
                headers=headers,
            )
        except HTTPException as exc:
            if exc.status_code == 502:
                raise HTTPException(status_code=502, detail=f"node_api_proxy_error: {str(exc.detail).removeprefix('proxy_error: ')}")
            raise
        return await self._proxy.stream_response(upstream)


def build_node_ui_proxy_router(proxy: NodeUiProxy) -> APIRouter:
    router = APIRouter()

    @router.api_route("/nodes/{node_id}/ui/{path:path}", methods=["GET", "HEAD"])
    async def proxy_node_ui_canonical(node_id: str, path: str, request: Request):
        return await proxy.forward(request, node_id, path, public_prefix=f"/nodes/{node_id}/ui")

    @router.api_route("/nodes/{node_id}/ui/", methods=["GET", "HEAD"])
    async def proxy_node_ui_canonical_root(node_id: str, request: Request):
        return await proxy.forward(request, node_id, "", public_prefix=f"/nodes/{node_id}/ui")

    @router.api_route("/nodes/{node_id}/ui", methods=["GET", "HEAD"])
    async def proxy_node_ui_canonical_root_no_slash(node_id: str, request: Request):
        return await proxy.forward(request, node_id, "", public_prefix=f"/nodes/{node_id}/ui")

    @router.api_route("/ui/nodes/{node_id}/{path:path}", methods=["GET", "HEAD"])
    async def proxy_node_ui(node_id: str, path: str, request: Request):
        return await proxy.forward(request, node_id, path, public_prefix=f"/ui/nodes/{node_id}")

    @router.api_route("/ui/nodes/{node_id}", methods=["GET", "HEAD"])
    async def proxy_node_ui_root(node_id: str, request: Request):
        return await proxy.forward(request, node_id, "", public_prefix=f"/ui/nodes/{node_id}")

    @router.api_route(
        "/api/nodes/{node_id}/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def proxy_node_api(node_id: str, path: str, request: Request):
        return await proxy.forward_api(request, node_id, path)

    @router.api_route(
        "/api/nodes/{node_id}/",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def proxy_node_api_root(node_id: str, request: Request):
        return await proxy.forward_api(request, node_id, "")

    @router.websocket("/nodes/{node_id}/ui/{path:path}")
    async def proxy_node_ui_canonical_websocket(node_id: str, path: str, websocket: WebSocket):
        await proxy.forward_websocket(websocket, node_id, path, public_prefix=f"/nodes/{node_id}/ui")

    @router.websocket("/nodes/{node_id}/ui/")
    async def proxy_node_ui_canonical_root_websocket(node_id: str, websocket: WebSocket):
        await proxy.forward_websocket(websocket, node_id, "", public_prefix=f"/nodes/{node_id}/ui")

    @router.websocket("/ui/nodes/{node_id}/{path:path}")
    async def proxy_node_ui_websocket(node_id: str, path: str, websocket: WebSocket):
        await proxy.forward_websocket(websocket, node_id, path, public_prefix=f"/ui/nodes/{node_id}")

    @router.websocket("/ui/nodes/{node_id}")
    async def proxy_node_ui_root_websocket(node_id: str, websocket: WebSocket):
        await proxy.forward_websocket(websocket, node_id, "", public_prefix=f"/ui/nodes/{node_id}")

    return router
