from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field


ImplementationStatus = Literal["Implemented", "Partially implemented", "Not implemented"]


class ClientApiEntry(BaseModel):
    name: str
    method: str
    api_path: str
    description: str
    status: ImplementationStatus
    authentication: str


class ClientCatalogEntry(BaseModel):
    name: str
    resource_type: str
    api_path: str
    description: str
    status: ImplementationStatus


class ClientSchemaEntry(BaseModel):
    name: str
    schema_id: str | None = None
    status: ImplementationStatus
    api_path: str


class ClientDocumentEntry(BaseModel):
    name: str
    title: str
    status: ImplementationStatus
    api_path: str


class SecurityProposalEntry(BaseModel):
    name: str
    status: Literal["Not implemented"] = "Not implemented"
    description: str
    proposed_api_path: str | None = None
    requirements: list[str] = Field(default_factory=list)


class ClientCoreCatalogResponse(BaseModel):
    schema_family: Literal["client-core"] = "client-core"
    version: Literal["v1"] = "v1"
    generated_at: str
    discovery: dict[str, str]
    current_security: dict[str, object]
    apis: list[ClientApiEntry]
    catalogs: list[ClientCatalogEntry]
    schemas: list[ClientSchemaEntry]
    documents: list[ClientDocumentEntry]
    security_proposals: list[SecurityProposalEntry]


README = """# Client Core V1 Catalog

Status: Implemented

This endpoint is the client-oriented discovery index for trusted Hexe nodes that
integrate with Core. It reports the current node onboarding, governance, service
resolution, authorization, budget, telemetry, and event-contract surfaces.

The primary discovery endpoint is `GET /api/schemas/client-core/v1`. Resolve the
listed `api_path` values against the Core base URL. The full generated API
contract remains available at `GET /openapi.json`.

## Security status

Core currently authenticates node-facing resolution and authorization calls
with `X-Node-Trust-Token`, issues short-lived HS256 service tokens after
governance and budget checks, and keeps the signing keys inside Core.

Provider-side service-token introspection is **not implemented**. Providers
cannot yet validate Core-issued HS256 tokens without Core signing material.
The proposed generic contract and rollout requirements are published at
`GET /api/schemas/client-core/v1/service-token-introspection-proposal.md` and
are explicitly non-operational.
"""


SECURITY_PROPOSAL = """# Core Service-Token Introspection Proposal

Status: Not implemented

This document describes a proposed security layer for every provider selected
through Core service resolution. It is not an available runtime contract.

## Proposed execution boundary

Resolution remains discovery. Core authorization issues a short-lived service
token, and the selected provider validates that token through Core before
executing the request.

Proposed endpoint:

`POST /api/system/nodes/services/introspect`

The provider would authenticate with `X-Node-Id` and its existing
`X-Node-Trust-Token`. Core would verify current node trust, provider ownership
of the JWT audience, signature against active and retained rotation keys,
expiration, subject, audience, scopes, issued-at time, and token identifier.

Authenticated inactive tokens would return HTTP 200 with `active=false` and a
stable error code. Missing provider credentials would return 401, invalid or
untrusted provider credentials 403, and abuse limiting 429.

## Proposed scope controls

Execution authorization would issue only `service.execute:<task_family>` from
the resolved and governed task. Provider catalog declarations could narrow but
could not expand authority. Privileged domain scopes would require explicit
Core-owned grants and could not be self-granted through provider metadata.

The proposed AI management scopes are `ai.prompts.read`, `ai.prompts.write`,
`ai.prompts.lifecycle`, `ai.prompts.review`, `ai.image_templates.read`,
`ai.image_templates.write`, `ai.image_templates.lifecycle`,
`ai.image_templates.review`, `ai.jobs.read`, `ai.jobs.cancel`,
`ai.artifacts.read`, `ai.artifacts.ack`, and `ai.services.read`.

## Proposed identity binding

JWT `sub` would identify the calling node. JWT `aud` would identify the exact
authorized logical provider service. Providers would require request identity
to match `sub` and the requested service to match `aud`.

## Rotation

Retired keys would remain verification-only for at least the maximum token
lifetime plus clock skew. No signing secret or key material would be returned
to a node.
"""


def _api(
    name: str,
    method: str,
    path: str,
    description: str,
    authentication: str = "X-Node-Trust-Token with node_id",
) -> ClientApiEntry:
    return ClientApiEntry(
        name=name,
        method=method,
        api_path=path,
        description=description,
        status="Implemented",
        authentication=authentication,
    )


def _catalog_payload() -> ClientCoreCatalogResponse:
    return ClientCoreCatalogResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        discovery={
            "openapi_path": "/openapi.json",
            "client_index_path": "/api/schemas/client-core/v1/README.md",
            "base_url_source": "configured Core API base URL",
        },
        current_security={
            "status": "Partially implemented",
            "node_authentication": "Trusted-node APIs authenticate with X-Node-Trust-Token and node_id.",
            "service_authorization": "Core resolution plus governance and budget checks issue short-lived service tokens.",
            "token_signing": "HS256 signing keys remain private to Core and rotate through the Core key ring.",
            "provider_token_verification": "Not implemented; the proposed introspection endpoint is not registered.",
        },
        apis=[
            _api("node_onboarding_start", "POST", "/api/system/nodes/onboarding/sessions", "Start node onboarding.", "Node onboarding proof contract"),
            _api("node_onboarding_finalize", "GET", "/api/system/nodes/onboarding/sessions/{session_id}/finalize", "Finalize an approved onboarding session.", "Onboarding session proof contract"),
            _api("node_reauthentication_start", "POST", "/api/system/nodes/reauth/sessions", "Start node reauthentication.", "Node reauthentication proof contract"),
            _api("node_reauthentication_finalize", "GET", "/api/system/nodes/reauth/sessions/{session_id}/finalize", "Finalize approved node reauthentication.", "Reauthentication session proof contract"),
            _api("capability_declaration", "POST", "/api/system/nodes/capabilities/declaration", "Submit the node capability declaration."),
            _api("provider_capability_report", "POST", "/api/system/nodes/providers/capabilities/report", "Publish provider, model, endpoint, and capacity capability state."),
            _api("governance_current", "GET", "/api/system/nodes/governance/current", "Fetch the current governance bundle and refresh freshness state."),
            _api("governance_refresh", "POST", "/api/system/nodes/governance/refresh", "Request a version-aware governance refresh."),
            _api("budget_declaration", "POST", "/api/system/nodes/budgets/declaration", "Declare node budget capabilities."),
            _api("budget_policy_current", "GET", "/api/system/nodes/budgets/policy/current", "Read the effective governed budget policy."),
            _api("budget_policy_refresh", "POST", "/api/system/nodes/budgets/policy/refresh", "Refresh the effective governed budget policy."),
            _api("budget_usage_summary", "POST", "/api/system/nodes/budgets/usage-summary", "Report usage against Core budget grants."),
            _api("service_resolve", "POST", "/api/system/nodes/services/resolve", "Resolve a task family to governed service candidates."),
            _api("service_authorize", "POST", "/api/system/nodes/services/authorize", "Authorize a resolved candidate and issue a short-lived service token."),
            _api("node_telemetry", "POST", "/api/system/nodes/telemetry", "Submit trusted-node telemetry."),
            _api("operational_status", "GET", "/api/system/nodes/operational-status/{node_id}", "Read node lifecycle, capability, and governance readiness."),
            _api("trust_status", "GET", "/api/system/nodes/trust-status/{node_id}", "Read explicit trust, revocation, and removal status."),
            _api("hardware_access_request", "POST", "/api/system/nodes/hardware/access-requests", "Request governed host-hardware access."),
            _api("hardware_lease_release", "POST", "/api/system/nodes/hardware/leases/{lease_id}/release", "Release a governed hardware lease."),
            _api("node_event_contract", "GET", "/api/system/mqtt/node-domain-events/contract", "Discover the direct node domain-event MQTT contract."),
        ],
        catalogs=[
            ClientCatalogEntry(name="capability_profiles", resource_type="node_capability_profiles", api_path="/api/system/nodes/capabilities/profiles", description="Accepted node capability profiles.", status="Implemented"),
            ClientCatalogEntry(name="governance_bundle", resource_type="node_governance", api_path="/api/system/nodes/governance/current", description="Current node governance, routing, and budget policy.", status="Implemented"),
            ClientCatalogEntry(name="service_candidates", resource_type="service_resolution", api_path="/api/system/nodes/services/resolve", description="Governed task-family service candidates.", status="Implemented"),
            ClientCatalogEntry(name="provider_routing_metadata", resource_type="provider_routing", api_path="/api/system/nodes/providers/routing-metadata", description="Current provider and model routing metadata.", status="Implemented"),
            ClientCatalogEntry(name="node_event_contract", resource_type="mqtt_event_contract", api_path="/api/system/mqtt/node-domain-events/contract", description="MQTT topics, envelope, QoS, and event-type requirements.", status="Implemented"),
        ],
        schemas=[
            ClientSchemaEntry(name="openapi.json", status="Implemented", api_path="/openapi.json"),
            ClientSchemaEntry(name="schema-catalog.v1.response.schema.json", schema_id="#/components/schemas/ClientCoreCatalogResponse", status="Implemented", api_path="/api/schemas/client-core/v1/schema-catalog.v1.response.schema.json"),
            ClientSchemaEntry(name="hardware-access-request.schema.json", status="Implemented", api_path="/api/system/nodes/hardware/access-requests/schema"),
        ],
        documents=[
            ClientDocumentEntry(name="README.md", title="Client Core V1 Catalog", status="Implemented", api_path="/api/schemas/client-core/v1/README.md"),
            ClientDocumentEntry(name="service-token-introspection-proposal.md", title="Core Service-Token Introspection Proposal", status="Not implemented", api_path="/api/schemas/client-core/v1/service-token-introspection-proposal.md"),
        ],
        security_proposals=[
            SecurityProposalEntry(
                name="provider_service_token_introspection",
                description="Allow a trusted provider node to validate a Core-issued service token without receiving Core signing secrets.",
                proposed_api_path="/api/system/nodes/services/introspect",
                requirements=[
                    "Authenticate the provider with X-Node-Id and X-Node-Trust-Token.",
                    "Require the provider to own the token audience.",
                    "Validate signature, claims, expiry, expected audience, and all required scopes.",
                    "Return stable inactive error codes and never log the submitted token.",
                    "Apply trusted-node rate limiting.",
                ],
            ),
            SecurityProposalEntry(
                name="universal_resolved_service_enforcement",
                description="Require every provider selected through service resolution to introspect the authorization token before execution.",
                requirements=[
                    "Treat resolution as discovery and authorization plus provider enforcement as the security boundary.",
                    "Bind request identity to JWT sub and the selected logical service to JWT aud.",
                    "Fail closed when Core introspection is unavailable or inactive.",
                ],
            ),
            SecurityProposalEntry(
                name="governed_privileged_scope_issuance",
                description="Issue privileged domain scopes only through explicit Core-owned authorization grants.",
                requirements=[
                    "Limit ordinary resolution authorization to service.execute:<task_family>.",
                    "Prevent provider catalog declarations from self-granting privileged scopes.",
                    "Require explicit Core grants for AI prompt, template, job, artifact, and service-management scopes.",
                ],
            ),
            SecurityProposalEntry(
                name="lifetime_based_rotation_retention",
                description="Retain retired verification keys until every token they signed must have expired.",
                requirements=[
                    "Retain keys for at least maximum token TTL plus clock skew.",
                    "Use retired keys only for verification and never expose key material.",
                ],
            ),
        ],
    )


def build_client_core_catalog_router() -> APIRouter:
    router = APIRouter(tags=["client-core-catalog"])

    @router.get("/schemas/client-core/v1", response_model=ClientCoreCatalogResponse)
    def get_client_core_catalog() -> ClientCoreCatalogResponse:
        return _catalog_payload()

    @router.get("/schemas/client-core/v1/schema-catalog.v1.response.schema.json")
    def get_client_core_catalog_schema() -> dict[str, object]:
        return ClientCoreCatalogResponse.model_json_schema()

    @router.get("/schemas/client-core/v1/README.md", response_class=PlainTextResponse)
    def get_client_core_readme() -> str:
        return README

    @router.get("/schemas/client-core/v1/service-token-introspection-proposal.md", response_class=PlainTextResponse)
    def get_service_token_introspection_proposal() -> str:
        return SECURITY_PROPOSAL

    return router
