from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.system.onboarding.registrations import NodeRegistrationsStore
from app.system.onboarding.trust import NodeTrustIssuanceService
from app.system.family_identity import FamilyIdentityStore
from app.system.service_access import ServiceAccessGrantStore

from .service import AssistantAssertionError, AssistantAssertionService


class AssistantAssertionIntrospectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1)
    expected_audience: str = Field(min_length=1)
    requester_node_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    required_scopes: list[str] = Field(default_factory=list)
    consume_approval: bool = False


class AssistantAssertionIntrospectionResponse(BaseModel):
    active: bool
    error_code: str | None = None
    claims: dict[str, Any] | None = None


class AssistantActorEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_type: str = Field(min_length=1, max_length=64)
    provider: str = Field(min_length=1, max_length=128)
    observed_at: str = Field(min_length=1, max_length=64)
    confidence_band: str | None = Field(default=None, max_length=32)
    verification_state: str | None = Field(default=None, max_length=32)


class AssistantActorAssertionIssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requester_node_id: str = Field(min_length=1, max_length=128)
    audience: str = Field(min_length=1, max_length=256)
    conversation_id: str = Field(min_length=1, max_length=128)
    turn_id: str = Field(min_length=1, max_length=128)
    actor_kind: Literal["person", "anonymous"]
    identity_state: Literal["verified", "probable", "unknown", "conflicted"]
    requested_scopes: list[str] = Field(min_length=1, max_length=16)
    person_id: str | None = Field(default=None, max_length=128)
    household_id: str | None = Field(default=None, max_length=128)
    room_id: str | None = Field(default=None, max_length=128)
    endpoint_id: str | None = Field(default=None, max_length=128)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[AssistantActorEvidenceRequest] = Field(default_factory=list, max_length=8)


class AssistantActorAssertionIssueResponse(BaseModel):
    token: str
    claims: dict[str, Any]
    grant_id: str


def build_assistant_auth_router(
    service: AssistantAssertionService,
    *,
    trust: NodeTrustIssuanceService | None = None,
    registrations: NodeRegistrationsStore | None = None,
    grants: ServiceAccessGrantStore | None = None,
    family: FamilyIdentityStore | None = None,
    issuer: str = "hexe-core",
) -> APIRouter:
    router = APIRouter(tags=["assistant-authorization"])

    @router.get("/.well-known/hexe-core-jwks.json")
    async def assistant_jwks() -> dict:
        return await service.keys.jwks()

    def require_trusted_node(node_id: str, node_token: str | None) -> Any:
        if not node_id:
            raise HTTPException(status_code=401, detail="node_identity_required")
        if not str(node_token or "").strip():
            raise HTTPException(status_code=401, detail="node_trust_token_required")
        if trust is None or registrations is None:
            raise HTTPException(status_code=503, detail="assistant_authorization_unavailable")
        registration = registrations.get(node_id)
        if trust.authenticate_node(node_id, str(node_token)) is None or registration is None:
            raise HTTPException(status_code=403, detail="untrusted_node")
        if str(registration.trust_status or "").strip().lower() != "trusted":
            raise HTTPException(status_code=403, detail="untrusted_node")
        return registration

    @router.post(
        "/api/system/nodes/assistant/actor-assertions",
        response_model=AssistantActorAssertionIssueResponse,
    )
    async def issue_actor_assertion(
        body: AssistantActorAssertionIssueRequest,
        x_node_id: str | None = Header(default=None),
        x_node_trust_token: str | None = Header(default=None),
    ) -> AssistantActorAssertionIssueResponse:
        caller_node_id = str(x_node_id or "").strip()
        require_trusted_node(caller_node_id, x_node_trust_token)
        if caller_node_id != body.requester_node_id:
            raise HTTPException(status_code=403, detail="assistant_requester_mismatch")
        parts = body.audience.split(":", 2)
        if len(parts) != 3 or parts[0] != "node-service" or parts[2] != "interaction.assistant.turn":
            raise HTTPException(status_code=403, detail="assistant_audience_invalid")
        provider = registrations.get(parts[1]) if registrations is not None else None
        provider_type = str(getattr(provider, "node_type", "") or "").strip().lower().removesuffix("-node")
        if provider is None or str(provider.trust_status or "").strip().lower() != "trusted" or provider_type != "interaction":
            raise HTTPException(status_code=403, detail="assistant_provider_invalid")
        clean_scopes = sorted({str(scope).strip() for scope in body.requested_scopes if str(scope).strip()})
        if any(scope not in {"assistant.turn.submit", "assistant.turn.cancel"} for scope in clean_scopes):
            raise HTTPException(status_code=403, detail="assistant_actor_scope_not_issuable")
        grant = grants.find_authorizing(subject_node_id=caller_node_id, audience=body.audience, required_scopes=clean_scopes) if grants is not None else None
        if grant is None:
            raise HTTPException(status_code=403, detail="assistant_service_access_not_authorized")

        person_id, household_id, room_id = body.person_id, body.household_id, body.room_id
        identity_state = body.identity_state
        snapshot = await family.snapshot() if family is not None else {"people": [], "endpoint_assignments": []}
        assignment = None
        if body.endpoint_id:
            assignment = next(
                (item for item in snapshot.get("endpoint_assignments", []) if item.get("endpoint_id") == body.endpoint_id),
                None,
            )
            if assignment is None:
                raise HTTPException(status_code=403, detail="assistant_endpoint_not_authorized")
            assigned_household = str(assignment.get("household_id") or "")
            assigned_room = str(assignment.get("room_id") or "")
            if household_id and household_id != assigned_household:
                raise HTTPException(status_code=403, detail="assistant_endpoint_context_mismatch")
            if room_id and room_id != assigned_room:
                raise HTTPException(status_code=403, detail="assistant_endpoint_context_mismatch")
            household_id, room_id = assigned_household, assigned_room
        if body.actor_kind == "anonymous":
            if person_id or identity_state not in {"unknown", "conflicted"}:
                raise HTTPException(status_code=422, detail="anonymous_actor_invalid")
        else:
            if not person_id or family is None:
                raise HTTPException(status_code=422, detail="person_actor_invalid")
            person = next((item for item in snapshot["people"] if item.get("person_id") == person_id and item.get("status") == "active"), None)
            if person is None or str(person.get("household_id") or "") != str(household_id or ""):
                raise HTTPException(status_code=403, detail="person_actor_not_authorized")
            if identity_state == "verified" and (body.confidence is None or body.confidence < 0.9 or not body.evidence):
                identity_state = "probable"
        if identity_state != "verified":
            clean_scopes = [scope for scope in clean_scopes if scope == "assistant.turn.submit"]
        if not clean_scopes:
            raise HTTPException(status_code=403, detail="assistant_actor_scope_not_issuable")

        token, claims = await service.issue_actor_assertion(
            core_id=issuer,
            audience=body.audience,
            requester_node_id=caller_node_id,
            conversation_id=body.conversation_id,
            turn_id=body.turn_id,
            actor_kind=body.actor_kind,
            identity_state=identity_state,
            scopes=clean_scopes,
            person_id=person_id,
            household_id=household_id,
            room_id=room_id,
            endpoint_id=body.endpoint_id,
            confidence=body.confidence,
            evidence=[item.model_dump() for item in body.evidence],
        )
        return AssistantActorAssertionIssueResponse(token=token, claims=claims, grant_id=grant.grant_id)

    @router.post(
        "/api/system/nodes/assistant/assertions/introspect",
        response_model=AssistantAssertionIntrospectionResponse,
    )
    async def introspect_assistant_assertion(
        body: AssistantAssertionIntrospectionRequest,
        x_node_id: str | None = Header(default=None),
        x_node_trust_token: str | None = Header(default=None),
    ) -> AssistantAssertionIntrospectionResponse:
        provider_node_id = str(x_node_id or "").strip()
        if not provider_node_id:
            raise HTTPException(status_code=401, detail="node_identity_required")
        if not str(x_node_trust_token or "").strip():
            raise HTTPException(status_code=401, detail="node_trust_token_required")
        require_trusted_node(provider_node_id, x_node_trust_token)
        if not body.expected_audience.startswith(f"node-service:{provider_node_id}:"):
            raise HTTPException(status_code=403, detail="assistant_assertion_audience_not_owned")
        try:
            claims = await service.introspect(
                body.token,
                audience=body.expected_audience,
                issuer=issuer,
                requester_node_id=body.requester_node_id,
                conversation_id=body.conversation_id,
                turn_id=body.turn_id,
                required_scopes=body.required_scopes,
                consume_approval=body.consume_approval,
            )
        except AssistantAssertionError as exc:
            return AssistantAssertionIntrospectionResponse(active=False, error_code=str(exc))
        return AssistantAssertionIntrospectionResponse(active=True, claims=claims)

    return router
