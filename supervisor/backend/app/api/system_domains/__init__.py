from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from fastapi import APIRouter

from .addons_runtime import build_addons_runtime_router
from .budgets import build_node_budgets_router
from .capabilities import build_node_capabilities_router
from .governance import build_node_governance_router
from .onboarding import build_node_onboarding_router
from .providers import build_node_providers_router
from .reauth import build_node_reauth_router
from .registrations import build_node_registration_router
from .routing import route_paths
from .services import build_node_services_router
from .telemetry import build_node_telemetry_router


DomainBuilder = Callable[[APIRouter], APIRouter]

DOMAIN_ROUTERS: tuple[tuple[str, DomainBuilder], ...] = (
    ("addons_runtime", build_addons_runtime_router),
    ("node_onboarding", build_node_onboarding_router),
    ("node_reauth", build_node_reauth_router),
    ("node_registrations", build_node_registration_router),
    ("node_capabilities", build_node_capabilities_router),
    ("node_budgets", build_node_budgets_router),
    ("node_services", build_node_services_router),
    ("node_providers", build_node_providers_router),
    ("node_governance", build_node_governance_router),
    ("node_telemetry", build_node_telemetry_router),
)


def compose_system_domain_router(source_router: APIRouter) -> APIRouter:
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
        raise RuntimeError(f"system_router_domain_assignment_invalid:{';'.join(detail)}")
    return router
