from __future__ import annotations

from fastapi import APIRouter

from ..system.hardware import HardwareAccessService
from . import system_legacy as _legacy
from .system_domains import compose_system_domain_router
from .system_legacy import *  # noqa: F401,F403

_RATE_WINDOWS = _legacy._RATE_WINDOWS


def build_system_router(
    registry: AddonRegistry,
    runtime_service: StandaloneRuntimeService | None = None,
    mqtt_manager=None,
    service_token_key_store=None,
    service_catalog_store: ServiceCatalogStore | None = None,
    mqtt_approval_service=None,
    mqtt_integration_state_store=None,
    mqtt_credential_store=None,
    mqtt_runtime_reconciler=None,
    onboarding_sessions_store: NodeOnboardingSessionsStore | None = None,
    node_reauth_sessions_store: NodeReauthSessionsStore | None = None,
    node_registrations_store: NodeRegistrationsStore | None = None,
    node_trust_issuance: NodeTrustIssuanceService | None = None,
    node_capability_acceptance: NodeCapabilityAcceptanceService | None = None,
    node_governance_service: NodeGovernanceService | None = None,
    node_governance_status_service: NodeGovernanceStatusService | None = None,
    node_telemetry_service: NodeTelemetryService | None = None,
    node_budget_service: NodeBudgetService | None = None,
    provider_model_policy_service=None,
    model_routing_registry_service: ModelRoutingRegistryService | None = None,
    supervisor_fleet_store=None,
    hardware_access_service: HardwareAccessService | None = None,
    audit_store: AuditLogStore | None = None,
) -> APIRouter:
    source_router = _legacy.build_system_router(
        registry=registry,
        runtime_service=runtime_service,
        mqtt_manager=mqtt_manager,
        service_token_key_store=service_token_key_store,
        service_catalog_store=service_catalog_store,
        mqtt_approval_service=mqtt_approval_service,
        mqtt_integration_state_store=mqtt_integration_state_store,
        mqtt_credential_store=mqtt_credential_store,
        mqtt_runtime_reconciler=mqtt_runtime_reconciler,
        onboarding_sessions_store=onboarding_sessions_store,
        node_reauth_sessions_store=node_reauth_sessions_store,
        node_registrations_store=node_registrations_store,
        node_trust_issuance=node_trust_issuance,
        node_capability_acceptance=node_capability_acceptance,
        node_governance_service=node_governance_service,
        node_governance_status_service=node_governance_status_service,
        node_telemetry_service=node_telemetry_service,
        node_budget_service=node_budget_service,
        provider_model_policy_service=provider_model_policy_service,
        model_routing_registry_service=model_routing_registry_service,
        supervisor_fleet_store=supervisor_fleet_store,
        hardware_access_service=hardware_access_service,
        audit_store=audit_store,
    )
    return compose_system_domain_router(source_router)
