from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from fastapi import APIRouter

from .audit import build_audit_router
from .catalog import build_catalog_router
from .install import build_install_router
from .lifecycle import build_lifecycle_router
from .routing import route_paths
from .sources import build_sources_router
from .status import build_status_router


DomainBuilder = Callable[[APIRouter], APIRouter]

DOMAIN_ROUTERS: tuple[tuple[str, DomainBuilder], ...] = (
    ("catalog", build_catalog_router),
    ("sources", build_sources_router),
    ("install", build_install_router),
    ("lifecycle", build_lifecycle_router),
    ("status", build_status_router),
    ("audit", build_audit_router),
)


def compose_store_domain_router(source_router: APIRouter) -> APIRouter:
    router = APIRouter()
    source_paths = route_paths(source_router)
    assigned_paths: list[str] = []
    for _name, builder in DOMAIN_ROUTERS:
        domain_router = builder(source_router)
        assigned_paths.extend(route_paths(domain_router))
        router.include_router(domain_router)

    assigned_counts = Counter(assigned_paths)
    duplicate_paths = sorted(path for path, count in assigned_counts.items() if count > 1)
    missing_paths = sorted(source_paths - set(assigned_paths))
    if duplicate_paths or missing_paths:
        detail = []
        if duplicate_paths:
            detail.append(f"duplicate={','.join(duplicate_paths)}")
        if missing_paths:
            detail.append(f"missing={','.join(missing_paths)}")
        raise RuntimeError(f"store_router_domain_assignment_invalid:{';'.join(detail)}")
    return router
