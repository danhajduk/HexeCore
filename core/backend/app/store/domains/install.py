from __future__ import annotations

from fastapi import APIRouter

from .routing import path_is, routes_matching


def build_install_router(source_router: APIRouter) -> APIRouter:
    return routes_matching(
        source_router,
        lambda path: path_is(path, "/install", "/update", "/uninstall"),
    )
