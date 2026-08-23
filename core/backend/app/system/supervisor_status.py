from __future__ import annotations

from typing import Any
import os
import time

from fastapi import APIRouter, Header, HTTPException, Request

from app.api.admin import require_admin_token
from app.supervisor.client import SupervisorApiClient


def build_supervisor_status_router() -> APIRouter:
    router = APIRouter()

    @router.get("/supervisor/summary")
    def supervisor_summary(request: Request) -> dict[str, Any]:
        client: SupervisorApiClient | None = getattr(request.app.state, "supervisor_client", None)
        if client is None:
            return {"ok": False, "error": "supervisor_client_unavailable"}

        cache = getattr(request.app.state, "supervisor_summary_cache", None)
        if not isinstance(cache, dict):
            cache = {"payload": None, "updated_at": 0.0}
            setattr(request.app.state, "supervisor_summary_cache", cache)

        ttl_s = 10
        raw_ttl = str(os.getenv("HEXE_SUPERVISOR_SUMMARY_CACHE_S", "")).strip()
        if raw_ttl:
            try:
                ttl_s = max(1, int(float(raw_ttl)))
            except Exception:
                ttl_s = 10

        now = time.time()
        cached_payload = cache.get("payload")
        cached_at = cache.get("updated_at")
        if isinstance(cached_payload, dict) and isinstance(cached_at, (int, float)) and now - cached_at < ttl_s:
            return cached_payload

        health = client.request_json("GET", "/api/supervisor/health")
        runtime = client.request_json("GET", "/api/supervisor/runtime")
        info = client.request_json("GET", "/api/supervisor/info")
        nodes = client.request_json("GET", "/api/supervisor/nodes")
        runtimes = client.request_json("GET", "/api/supervisor/runtimes")
        core_runtimes = client.request_json("GET", "/api/supervisor/core/runtimes")

        available = any(item is not None for item in (health, runtime, info, nodes, runtimes, core_runtimes))
        if not available:
            payload = {"ok": False, "error": "supervisor_unavailable"}
            cache["payload"] = payload
            cache["updated_at"] = now
            return payload

        payload = {
            "ok": True,
            "available": True,
            "health": health,
            "runtime": runtime,
            "info": info,
            "nodes": nodes.get("items", []) if isinstance(nodes, dict) else [],
            "runtimes": runtimes.get("items", []) if isinstance(runtimes, dict) else [],
            "core_runtimes": core_runtimes.get("items", []) if isinstance(core_runtimes, dict) else [],
        }
        cache["payload"] = payload
        cache["updated_at"] = now
        return payload

    @router.get("/supervisor/resources/history")
    def supervisor_resource_history(
        request: Request,
        range: str = "24h",  # noqa: A002
        step: str | None = "60s",
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        client: SupervisorApiClient | None = getattr(request.app.state, "supervisor_client", None)
        if client is None:
            raise HTTPException(status_code=503, detail="supervisor_client_unavailable")
        payload = client.resource_history(range_value=range, step_value=step)
        if payload is None:
            raise HTTPException(status_code=502, detail="supervisor_unavailable")
        return payload

    @router.get("/supervisor/runtimes/{node_id}/resources/history")
    def supervisor_runtime_resource_history(
        node_id: str,
        request: Request,
        range: str = "24h",  # noqa: A002
        step: str | None = "60s",
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        client: SupervisorApiClient | None = getattr(request.app.state, "supervisor_client", None)
        if client is None:
            raise HTTPException(status_code=503, detail="supervisor_client_unavailable")
        payload = client.runtime_resource_history(node_id, range_value=range, step_value=step)
        if payload is None:
            raise HTTPException(status_code=502, detail="supervisor_unavailable")
        return payload

    @router.get("/supervisor/core/runtimes/{runtime_id}/resources/history")
    def supervisor_core_runtime_resource_history(
        runtime_id: str,
        request: Request,
        range: str = "24h",  # noqa: A002
        step: str | None = "60s",
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        client: SupervisorApiClient | None = getattr(request.app.state, "supervisor_client", None)
        if client is None:
            raise HTTPException(status_code=503, detail="supervisor_client_unavailable")
        payload = client.core_runtime_resource_history(runtime_id, range_value=range, step_value=step)
        if payload is None:
            raise HTTPException(status_code=502, detail="supervisor_unavailable")
        return payload

    return router
