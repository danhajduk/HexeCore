from __future__ import annotations

from fastapi import APIRouter

from .routing import path_is, path_starts, routes_matching


def build_debug_router(source_router: APIRouter) -> APIRouter:
    return routes_matching(
        source_router,
        lambda path: path_starts(path, "/debug/")
        or path_starts(path, "/mqtt/debug/")
        or path_is(path, "/mqtt/debug/notifications/test-flow"),
    )
