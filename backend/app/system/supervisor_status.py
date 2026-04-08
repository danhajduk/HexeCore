from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.supervisor.client import SupervisorApiClient


def build_supervisor_status_router() -> APIRouter:
    router = APIRouter()

    @router.get("/supervisor/summary")
    def supervisor_summary(request: Request) -> dict[str, Any]:
        client: SupervisorApiClient | None = getattr(request.app.state, "supervisor_client", None)
        if client is None:
            return {"ok": False, "error": "supervisor_client_unavailable"}

        health = client.request_json("GET", "/api/supervisor/health")
        runtime = client.request_json("GET", "/api/supervisor/runtime")
        info = client.request_json("GET", "/api/supervisor/info")
        nodes = client.request_json("GET", "/api/supervisor/nodes")
        runtimes = client.request_json("GET", "/api/supervisor/runtimes")
        core_runtimes = client.request_json("GET", "/api/supervisor/core/runtimes")

        available = any(item is not None for item in (health, runtime, info, nodes, runtimes, core_runtimes))
        if not available:
            return {"ok": False, "error": "supervisor_unavailable"}

        return {
            "ok": True,
            "available": True,
            "health": health,
            "runtime": runtime,
            "info": info,
            "nodes": nodes.get("items", []) if isinstance(nodes, dict) else [],
            "runtimes": runtimes.get("items", []) if isinstance(runtimes, dict) else [],
            "core_runtimes": core_runtimes.get("items", []) if isinstance(core_runtimes, dict) else [],
        }

    return router
