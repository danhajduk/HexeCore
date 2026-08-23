from __future__ import annotations

from fastapi import APIRouter

from .routing import path_is, path_starts, routes_matching


def build_addons_runtime_router(source_router: APIRouter) -> APIRouter:
    return routes_matching(
        source_router,
        lambda path: path_is(path, "/addons", "/addons/{addon_id}/enable", "/addons/errors")
        or path_starts(path, "/system/addons/runtime"),
    )
