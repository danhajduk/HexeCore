from __future__ import annotations

from fastapi import APIRouter

from .models import SupervisorHealthSummary, SupervisorInfoSummary
from .service import SupervisorDomainService


def build_supervisor_router(service: SupervisorDomainService | None = None) -> APIRouter:
    router = APIRouter(tags=["supervisor"])
    supervisor = service or SupervisorDomainService()

    @router.get("/supervisor/health")
    def get_supervisor_health() -> SupervisorHealthSummary:
        return supervisor.health_summary()

    @router.get("/supervisor/info")
    def get_supervisor_info() -> SupervisorInfoSummary:
        return supervisor.info_summary()

    return router
