from __future__ import annotations

from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import HTTPException

from .models import EdgePublication

ALLOWED_UPSTREAM_HOSTS = {"127.0.0.1", "localhost"}
BLOCKED_HEADERS = {
    "host",
    "connection",
    "content-length",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-forwarded-for",
}


class EdgeProxyService:
    def __init__(self, *, timeout_s: float = 15.0) -> None:
        self._timeout = timeout_s

    def validate_upstream(self, upstream_base_url: str) -> None:
        parsed = urlsplit(str(upstream_base_url or "").strip())
        if parsed.scheme not in {"http", "https"}:
            raise HTTPException(status_code=400, detail="edge_target_scheme_invalid")
        if parsed.hostname not in ALLOWED_UPSTREAM_HOSTS:
            raise HTTPException(status_code=400, detail="edge_target_host_not_allowed")

    async def forward(
        self,
        *,
        publication: EdgePublication,
        method: str,
        path: str,
        query_string: str,
        headers: dict[str, str],
        body: bytes,
    ) -> tuple[int, bytes, dict[str, str]]:
        self.validate_upstream(publication.target.upstream_base_url)
        for prefix in publication.target.allowed_path_prefixes:
            if path.startswith(prefix):
                break
        else:
            raise HTTPException(status_code=403, detail="edge_proxy_path_not_allowed")

        url = urljoin(publication.target.upstream_base_url.rstrip("/") + "/", path.lstrip("/"))
        if query_string:
            url = f"{url}?{query_string}"
        safe_headers = {k: v for k, v in headers.items() if k.lower() not in BLOCKED_HEADERS}
        safe_headers["x-hexe-edge-publication"] = publication.publication_id
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
            response = await client.request(method=method, url=url, content=body, headers=safe_headers)
        return response.status_code, response.content, dict(response.headers)
