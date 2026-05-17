from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse


RESERVED_BACKEND_PREFIXES = {"api", "ui"}
RESERVED_PROXY_PREFIXES = {
    ("addons", "proxy"),
    ("nodes", "proxy"),
}


def default_frontend_dist_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def configured_frontend_dist_dir() -> Path:
    raw = str(os.getenv("HEXE_FRONTEND_DIST_DIR", "")).strip()
    return Path(raw).expanduser() if raw else default_frontend_dist_dir()


def frontend_serving_enabled() -> bool:
    raw = str(os.getenv("HEXE_SERVE_FRONTEND", "1")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _is_reserved_backend_path(path: str) -> bool:
    parts = [part for part in path.split("/") if part]
    if not parts:
        return False
    if parts[0] in RESERVED_BACKEND_PREFIXES:
        return True
    return len(parts) >= 2 and (parts[0], parts[1]) in RESERVED_PROXY_PREFIXES


def _safe_static_path(root: Path, request_path: str) -> Path | None:
    candidate = (root / request_path.lstrip("/")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def build_frontend_static_router(dist_dir: Path | None = None) -> APIRouter | None:
    if not frontend_serving_enabled():
        return None

    root = (dist_dir or configured_frontend_dist_dir()).resolve()
    index = root / "index.html"
    if not index.is_file():
        return None

    router = APIRouter()

    async def serve_frontend(request: Request, path: str = "") -> FileResponse:
        safe_path = _safe_static_path(root, path)
        if safe_path is None:
            raise HTTPException(status_code=404, detail="not_found")

        if safe_path.is_dir():
            nested_index = safe_path / "index.html"
            if nested_index.is_file():
                return FileResponse(nested_index)

        if safe_path.is_file():
            return FileResponse(safe_path)

        if _is_reserved_backend_path(path) or Path(path).suffix:
            raise HTTPException(status_code=404, detail="not_found")

        return FileResponse(index)

    router.add_api_route("/", serve_frontend, methods=["GET", "HEAD"], include_in_schema=False)
    router.add_api_route("/{path:path}", serve_frontend, methods=["GET", "HEAD"], include_in_schema=False)
    return router
