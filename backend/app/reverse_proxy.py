from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any
import re
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from fastapi import HTTPException, Request
from starlette.background import BackgroundTask
from starlette.responses import HTMLResponse, Response, StreamingResponse
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect as websocket_connect
from websockets.exceptions import ConnectionClosed

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
    "origin",
    "range",
    "user-agent",
}

HTML_ROOT_URL_ATTR_RE = re.compile(r'(?P<prefix>\b(?:src|href|action)=["\'])(?P<path>/[^"\']*)')
ROOT_URL_STRING_RE = re.compile(r'(?P<quote>["\'])(?P<path>/[^"\']*)(?P=quote)')


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

    @staticmethod
    def rewrite_root_relative_urls(
        content: bytes,
        content_type: str | None,
        *,
        proxy_prefix: str,
        ignore_prefixes: tuple[str, ...] = (),
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

        normalized_proxy_prefix = proxy_prefix.rstrip("/")

        def should_rewrite(path: str) -> bool:
            if not path.startswith("/"):
                return False
            if path == "/":
                return False
            for prefix in ignore_prefixes:
                normalized = str(prefix or "").rstrip("/")
                if normalized and (path == normalized or path.startswith(f"{normalized}/")):
                    return False
            return True

        rewritten = text
        if is_html:
            rewritten = HTML_ROOT_URL_ATTR_RE.sub(
                lambda match: (
                    f"{match.group('prefix')}{normalized_proxy_prefix}{match.group('path')}"
                    if should_rewrite(match.group("path"))
                    else match.group(0)
                ),
                rewritten,
            )
        rewritten = ROOT_URL_STRING_RE.sub(
            lambda match: (
                f"{match.group('quote')}{normalized_proxy_prefix}{match.group('path')}{match.group('quote')}"
                if should_rewrite(match.group("path"))
                else match.group(0)
            ),
            rewritten,
        )
        return rewritten.encode("utf-8")

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

    @staticmethod
    def build_ui_error_response(
        *,
        status_code: int,
        detail: str,
        title: str,
        target_label: str,
        public_prefix: str,
    ) -> HTMLResponse:
        escaped_title = str(title)
        escaped_detail = str(detail)
        escaped_label = str(target_label)
        escaped_prefix = str(public_prefix)
        return HTMLResponse(
            status_code=status_code,
            content=(
                "<!doctype html><html><head><meta charset='utf-8'>"
                f"<title>{escaped_title}</title>"
                "<style>"
                "body{font-family:system-ui,sans-serif;background:#f6f7f9;color:#1f2937;"
                "margin:0;padding:24px;}main{max-width:720px;margin:0 auto;background:#fff;"
                "border:1px solid #d1d5db;border-radius:14px;padding:24px;}"
                "h1{margin:0 0 12px;font-size:1.2rem;}p{margin:8px 0;line-height:1.5;}"
                "code{background:#f3f4f6;padding:2px 6px;border-radius:6px;}"
                "</style></head><body><main>"
                f"<h1>{escaped_title}</h1>"
                f"<p>The proxied UI for <strong>{escaped_label}</strong> is currently unavailable.</p>"
                f"<p>Reason: <code>{escaped_detail}</code></p>"
                f"<p>Proxy path: <code>{escaped_prefix}</code></p>"
                "</main></body></html>"
            ),
        )

    @staticmethod
    def build_websocket_target_url(target_base: str, path: str, query: str = "", *, safe_path_chars: str = "/@:") -> str:
        target = ReverseProxyService.build_target_url(target_base, path, query, safe_path_chars=safe_path_chars)
        parsed = urlsplit(target)
        scheme = parsed.scheme
        if scheme == "http":
            scheme = "ws"
        elif scheme == "https":
            scheme = "wss"
        return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))

    def build_websocket_headers(
        self,
        websocket: WebSocket,
        *,
        public_prefix: str,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in websocket.headers.items():
            lowered = key.lower()
            if lowered in HOP_BY_HOP_HEADERS or lowered == "origin" or lowered == "sec-websocket-protocol":
                continue
            if lowered not in self._request_header_allowlist:
                continue
            headers[key] = value
        headers["X-Forwarded-Host"] = websocket.headers.get("host", websocket.url.netloc)
        headers["X-Forwarded-Proto"] = websocket.url.scheme
        headers["X-Forwarded-Prefix"] = public_prefix.rstrip("/") or "/"
        for key, value in (extra_headers or {}).items():
            if str(key).strip() and str(value).strip():
                headers[str(key)] = str(value)
        return headers

    @staticmethod
    def websocket_subprotocols(websocket: WebSocket) -> list[str]:
        raw = str(websocket.headers.get("sec-websocket-protocol", "") or "").strip()
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    async def proxy_websocket(
        self,
        websocket: WebSocket,
        *,
        target_url: str,
        public_prefix: str,
        extra_headers: dict[str, str] | None = None,
        open_timeout: float = 10.0,
    ) -> None:
        origin = str(websocket.headers.get("origin", "") or "").strip() or None
        subprotocols = self.websocket_subprotocols(websocket)
        upstream_headers = self.build_websocket_headers(
            websocket,
            public_prefix=public_prefix,
            extra_headers=extra_headers,
        )
        try:
            async with websocket_connect(
                target_url,
                origin=origin,
                subprotocols=subprotocols or None,
                additional_headers=upstream_headers,
                user_agent_header=websocket.headers.get("user-agent"),
                open_timeout=open_timeout,
            ) as upstream:
                await websocket.accept(subprotocol=upstream.subprotocol)

                async def client_to_upstream() -> None:
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            await upstream.close(
                                code=int(message.get("code") or 1000),
                                reason=str(message.get("reason") or ""),
                            )
                            return
                        if message.get("text") is not None:
                            await upstream.send(message["text"])
                        elif message.get("bytes") is not None:
                            await upstream.send(message["bytes"])

                async def upstream_to_client() -> None:
                    try:
                        async for message in upstream:
                            if isinstance(message, bytes):
                                await websocket.send_bytes(message)
                            else:
                                await websocket.send_text(message)
                    except ConnectionClosed as exc:
                        await websocket.close(code=exc.code or 1000, reason=exc.reason or "")

                try:
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(client_to_upstream())
                        tg.create_task(upstream_to_client())
                except* WebSocketDisconnect as group:
                    exc = group.exceptions[0]
                    await upstream.close(code=exc.code, reason=getattr(exc, "reason", "") or "")
        except Exception:
            await websocket.close(code=1011, reason="proxy_connect_failed")
