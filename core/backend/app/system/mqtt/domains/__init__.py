from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from fastapi import APIRouter

from .bridge_grants import build_bridge_grants_router
from .debug import build_debug_router
from .grants import build_grants_router
from .observability import build_observability_router
from .principals import build_principals_router
from .provisioning import build_provisioning_router
from .routing import route_paths
from .runtime import build_runtime_router
from .setup import build_setup_router


DomainBuilder = Callable[[APIRouter], APIRouter]

DOMAIN_ROUTERS: tuple[tuple[str, DomainBuilder], ...] = (
    ("setup", build_setup_router),
    ("debug", build_debug_router),
    ("runtime", build_runtime_router),
    ("provisioning", build_provisioning_router),
    ("bridge_grants", build_bridge_grants_router),
    ("grants", build_grants_router),
    ("principals", build_principals_router),
    ("observability", build_observability_router),
)


def compose_mqtt_domain_router(source_router: APIRouter) -> APIRouter:
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
        raise RuntimeError(f"mqtt_router_domain_assignment_invalid:{';'.join(detail)}")
    return router
