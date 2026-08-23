from __future__ import annotations

import sys
import types

from fastapi import APIRouter

from . import router_legacy as _legacy
from .domains import compose_store_domain_router

globals().update({name: value for name, value in _legacy.__dict__.items() if not name.startswith("__")})


class _StoreRouterModule(types.ModuleType):
    def __setattr__(self, name: str, value):  # noqa: ANN001
        super().__setattr__(name, value)
        if hasattr(_legacy, name):
            setattr(_legacy, name, value)


sys.modules[__name__].__class__ = _StoreRouterModule


def build_store_router(
    registry: AddonRegistry,
    audit_store: StoreAuditLogStore,
    sources_store: StoreSourcesStore | None = None,
    catalog_client: CatalogCacheClient | None = None,
    runtime_service: StandaloneRuntimeService | None = None,
    events: PlatformEventService | None = None,
    mqtt_approval_service=None,
) -> APIRouter:
    source_router = _legacy.build_store_router(
        registry=registry,
        audit_store=audit_store,
        sources_store=sources_store,
        catalog_client=catalog_client,
        runtime_service=runtime_service,
        events=events,
        mqtt_approval_service=mqtt_approval_service,
    )
    return compose_store_domain_router(source_router)
