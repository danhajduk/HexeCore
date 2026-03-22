from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException, Request
from starlette.background import BackgroundTask
from starlette.responses import Response, StreamingResponse

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

DEFAULT_REQUEST_HEADER_ALLOWLIST = {
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


class ReverseProxyService:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        request_header_allowlist: Iterable[str] | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(follow_redirects=False)
        self._request_header_allowlist = {
            str(item).strip().lower()
            for item in (request_header_allowlist or DEFAULT_REQUEST_HEADER_ALLOWLIST)
            if str(item).strip()
        }

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def build_target_url(target_base: str, path: str, query: str = "", *, safe_path_chars: str = "/@:") -> str:
        target = f"{target_base}/{quote(path.lstrip('/'), safe=safe_path_chars)}" if path else target_base
        if query:
            target = f"{target}?{query}"
        return target

    def build_request_headers(
        self,
        request: Request,
        *,
        public_prefix: str,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in request.headers.items():
            lowered = key.lower()
            if lowered in HOP_BY_HOP_HEADERS:
                continue
            if lowered not in self._request_header_allowlist:
                continue
            headers[key] = value
        headers["X-Forwarded-Host"] = request.headers.get("host", request.url.netloc)
        headers["X-Forwarded-Proto"] = request.url.scheme
        headers["X-Forwarded-Prefix"] = public_prefix.rstrip("/") or "/"
        for key, value in (extra_headers or {}).items():
            if str(key).strip() and str(value).strip():
                headers[str(key)] = str(value)
        return headers

    @staticmethod
    def safe_response_headers(source: httpx.Headers) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in source.items():
            if key.lower() in HOP_BY_HOP_HEADERS:
                continue
            headers[key] = value
        return headers

    async def send(
        self,
        *,
        request: Request,
        target_url: str,
        headers: dict[str, str],
        timeout: httpx.Timeout | float | None = None,
        content: Any = None,
    ) -> httpx.Response:
        upstream_request = self._client.build_request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=request.stream() if content is None else content,
        )
        if timeout is not None:
            resolved_timeout = timeout if isinstance(timeout, httpx.Timeout) else httpx.Timeout(timeout)
            upstream_request.extensions["timeout"] = resolved_timeout.as_dict()
        try:
            return await self._client.send(upstream_request, stream=True)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"proxy_error: {type(exc).__name__}")

    async def stream_response(self, upstream: httpx.Response) -> Response:
        return StreamingResponse(
            upstream.aiter_raw(),
            status_code=upstream.status_code,
            headers=self.safe_response_headers(upstream.headers),
            background=BackgroundTask(upstream.aclose),
        )
