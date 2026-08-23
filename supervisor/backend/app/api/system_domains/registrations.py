from __future__ import annotations

from fastapi import APIRouter

from .routing import path_is, path_starts, routes_matching


def build_node_registration_router(source_router: APIRouter) -> APIRouter:
    return routes_matching(
        source_router,
        lambda path: path_starts(path, "/system/nodes/registrations")
        or path_is(path, "/system/nodes/registry")
        or path_starts(path, "/system/nodes/trust-status", "/system/nodes/operational-status"),
    )
