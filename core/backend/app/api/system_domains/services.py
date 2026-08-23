from __future__ import annotations

from fastapi import APIRouter

from .routing import path_starts, routes_matching


def build_node_services_router(source_router: APIRouter) -> APIRouter:
    return routes_matching(source_router, lambda path: path_starts(path, "/system/nodes/services"))
