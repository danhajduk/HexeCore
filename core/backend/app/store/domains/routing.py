from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter


RoutePredicate = Callable[[str], bool]


def route_paths(router: APIRouter) -> set[str]:
    return {str(getattr(route, "path", "")) for route in router.routes if str(getattr(route, "path", ""))}


def routes_matching(source_router: APIRouter, predicate: RoutePredicate) -> APIRouter:
    router = APIRouter()
    for route in source_router.routes:
        path = str(getattr(route, "path", ""))
        if path and predicate(path):
            router.routes.append(route)
    return router


def path_is(path: str, *values: str) -> bool:
    return path in values


def path_starts(path: str, *prefixes: str) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)
