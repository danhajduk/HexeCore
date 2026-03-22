from __future__ import annotations

from urllib.parse import quote, urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from .service import NodesDomainService

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

REQUEST_HEADER_ALLOWLIST = {
    "accept",
    "accept-encoding",
    "accept-language",
    "cache-control",
    "content-type",
    "if-match",
    "if-none-match",
    "if-modified-since",
    "if-unmodified-since",
    "range",
    "user-agent",
}


class NodeUiProxy:
    def __init__(self, service: NodesDomainService) -> None:
        self._service = service
        self._client = httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(10.0))

    async def aclose(self) -> None:
        await self._client.aclose()

    def _target_base(self, node_id: str, request: Request) -> str:
        node = self._service.get_node(node_id)
        raw_endpoint = str(getattr(node, "requested_ui_endpoint", "") or "").strip()
        if raw_endpoint:
            parsed = urlsplit(raw_endpoint)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return raw_endpoint.rstrip("/")
            raise HTTPException(status_code=502, detail="node_ui_endpoint_invalid")
        raw_host = str(getattr(node, "requested_hostname", "") or "").strip()
        if not raw_host:
            raise HTTPException(status_code=404, detail="node_ui_endpoint_not_configured")
        if raw_host.startswith("http://") or raw_host.startswith("https://"):
            return raw_host.rstrip("/")
        scheme = "https" if request.url.scheme == "https" else "http"
        return f"{scheme}://{raw_host.rstrip('/')}"

    def _safe_request_headers(self, request: Request) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in request.headers.items():
            lk = key.lower()
            if lk in HOP_BY_HOP_HEADERS or lk not in REQUEST_HEADER_ALLOWLIST:
                continue
            headers[key] = value
        return headers

    @staticmethod
    def _safe_response_headers(source: httpx.Headers) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in source.items():
            if key.lower() in HOP_BY_HOP_HEADERS:
                continue
            headers[key] = value
        return headers

    async def forward(self, request: Request, node_id: str, path: str = "") -> Response:
        target_base = self._target_base(node_id, request)
        target = f"{target_base}/{quote(path.lstrip('/'), safe='/')}" if path else target_base
        if request.url.query:
            target = f"{target}?{request.url.query}"
        body = await request.body()
        try:
            upstream = await self._client.request(
                method=request.method,
                url=target,
                content=body,
                headers=self._safe_request_headers(request),
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"node_ui_proxy_error: {type(exc).__name__}")
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=self._safe_response_headers(upstream.headers),
        )


def build_node_ui_proxy_router(proxy: NodeUiProxy) -> APIRouter:
    router = APIRouter()

    @router.api_route("/ui/nodes/{node_id}/{path:path}", methods=["GET", "HEAD"])
    async def proxy_node_ui(node_id: str, path: str, request: Request):
        return await proxy.forward(request, node_id, path)

    @router.api_route("/ui/nodes/{node_id}", methods=["GET", "HEAD"])
    async def proxy_node_ui_root(node_id: str, request: Request):
        return await proxy.forward(request, node_id, "")

    return router
