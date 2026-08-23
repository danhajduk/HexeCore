from __future__ import annotations

from fastapi import APIRouter

from . import router_legacy as _legacy
from .acl_compiler import MqttAclCompiler
from .approval import MqttRegistrationApprovalService
from .domains import compose_mqtt_domain_router
from .integration_state import MqttIntegrationStateStore
from .manager import MqttManager
from .router_legacy import *  # noqa: F401,F403

from app.system.auth import ServiceTokenKeyStore
from app.system.onboarding import NodeRegistrationsStore, NodeTrustIssuanceService


def build_mqtt_router(
    manager: MqttManager,
    registry,
    state_store: MqttIntegrationStateStore,
    key_store: ServiceTokenKeyStore,
    settings_store=None,
    approval_service: MqttRegistrationApprovalService | None = None,
    acl_compiler: MqttAclCompiler | None = None,
    credential_store=None,
    runtime_reconciler=None,
    runtime_boundary=None,
    observability_store=None,
    audit_store=None,
    node_registrations_store: NodeRegistrationsStore | None = None,
    node_trust_issuance: NodeTrustIssuanceService | None = None,
) -> APIRouter:
    source_router = _legacy.build_mqtt_router(
        manager=manager,
        registry=registry,
        state_store=state_store,
        key_store=key_store,
        settings_store=settings_store,
        approval_service=approval_service,
        acl_compiler=acl_compiler,
        credential_store=credential_store,
        runtime_reconciler=runtime_reconciler,
        runtime_boundary=runtime_boundary,
        observability_store=observability_store,
        audit_store=audit_store,
        node_registrations_store=node_registrations_store,
        node_trust_issuance=node_trust_issuance,
    )
    return compose_mqtt_domain_router(source_router)
