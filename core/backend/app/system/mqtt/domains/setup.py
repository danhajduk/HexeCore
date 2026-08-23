from __future__ import annotations

from fastapi import APIRouter

from .routing import path_is, routes_matching


def build_setup_router(source_router: APIRouter) -> APIRouter:
    return routes_matching(
        source_router,
        lambda path: path_is(
            path,
            "/mqtt/status",
            "/mqtt/test",
            "/mqtt/restart",
            "/mqtt/reload",
            "/mqtt/setup/test-connection",
            "/mqtt/setup/apply",
            "/mqtt/setup-summary",
            "/mqtt/health",
            "/mqtt/bootstrap/publish",
            "/mqtt/setup-state",
        ),
    )
