from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.system.onboarding.registrations import NodeRegistrationsStore
from app.system.onboarding.trust import NodeTrustIssuanceService
from app.system.family_identity import FamilyIdentityStore
from app.system.service_access import ServiceAccessGrantStore
from app.system.users.store import UsersStore
from app.system.auth import ServiceTokenError, ServiceTokenKeyStore, validate_claims, verify_hs256

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


class IntentExecutionAuthorizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_assertion: str = Field(min_length=1)
    requester_node_id: str = Field(min_length=1, max_length=128)
    interaction_audience: str = Field(min_length=1, max_length=256)
    owner_audience: str = Field(min_length=1, max_length=256)
    conversation_id: str = Field(min_length=1, max_length=128)
    turn_id: str = Field(min_length=1, max_length=128)
    intent_id: str = Field(min_length=1, max_length=160)
    contract_version: str = Field(min_length=1, max_length=64)
    intent_revision: str = Field(min_length=1, max_length=64)
    action: str = Field(min_length=1, max_length=160)
    target_capability: str = Field(min_length=1, max_length=160)
    canonical_arguments_hash: str = Field(min_length=64, max_length=64)
    correlation_id: str = Field(min_length=1, max_length=160)
    required_scopes: list[str] = Field(default_factory=list, max_length=16)
    risk: Literal["ordinary", "admin"] = "ordinary"


class IntentExecutionIntrospectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorization_ref: str = Field(min_length=1)
    intent_id: str = Field(min_length=1, max_length=160)
    contract_version: str = Field(min_length=1, max_length=64)
    intent_revision: str = Field(min_length=1, max_length=64)
    action: str = Field(min_length=1, max_length=160)
    target_capability: str = Field(min_length=1, max_length=160)
    canonical_arguments_hash: str = Field(min_length=64, max_length=64)
    correlation_id: str = Field(min_length=1, max_length=160)
    consume: bool = True


class IntentExecutionAuthorizeResponse(BaseModel):
    ok: bool = True
    contract_version: Literal["assistant.intent-execution-authorization.v1"]
    authorization_ref: str
    owner_audience: str
    expires_at: int


class IntentExecutionIntrospectionResponse(BaseModel):
    active: bool
    error_code: str | None = None
    actor_id: str | None = None
    identity_state: str | None = None
    effective_scopes: list[str] = Field(default_factory=list)
    expires_at: int | None = None
    replayed: bool = False


class SpeakerEnrollmentGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    person_id: str = Field(min_length=1, max_length=128)
    endpoint_id: str = Field(min_length=1, max_length=128)
    enrollment_session_id: str = Field(min_length=1, max_length=128)


class SpeakerEnrollmentGrantConsumeRequest(SpeakerEnrollmentGrantRequest):
    grant_ref: str = Field(min_length=1)


class SpeakerEnrollmentPerson(BaseModel):
    person_id: str
    enrollment_label: str
    consent_state: Literal["granted"]
    eligibility_state: Literal["eligible"]
    enrollment_status: Literal["available"]
    reason: str | None = None


class SpeakerEnrollmentDirectoryResponse(BaseModel):
    ok: bool = True
    contract_version: Literal["voice.speaker-enrollment.v1"]
    household_id: str
    enrollment_session_id: str
    items: list[SpeakerEnrollmentPerson]
    next_cursor: int | None = None


class SpeakerEnrollmentGrantResponse(BaseModel):
    ok: bool = True
    contract_version: Literal["voice.speaker-enrollment.v1"]
    grant_ref: str
    expires_at: int
    purpose: Literal["speaker-recognition"]


def build_assistant_auth_router(
    service: AssistantAssertionService,
    *,
    trust: NodeTrustIssuanceService | None = None,
    registrations: NodeRegistrationsStore | None = None,
    grants: ServiceAccessGrantStore | None = None,
    family: FamilyIdentityStore | None = None,
    users: UsersStore | None = None,
    service_token_keys: ServiceTokenKeyStore | None = None,
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

    def require_voice_enrollment_access(node_id: str, endpoint_id: str, *, scope: str = "assistant.speaker_enrollment.read") -> tuple[Any, str, dict[str, Any]]:
        registration = registrations.get(node_id) if registrations is not None else None
        node_type = str(getattr(registration, "node_type", "") or "").strip().lower().removesuffix("-node")
        if node_type != "voice":
            raise HTTPException(status_code=403, detail="speaker_enrollment_voice_required")
        audience = f"core-service:{issuer}:voice.speaker-enrollment"
        grant = grants.find_authorizing(subject_node_id=node_id, audience=audience, required_scopes=[scope]) if grants is not None else None
        if grant is None:
            raise HTTPException(status_code=403, detail="speaker_enrollment_not_authorized")
        return registration, audience, {"endpoint_id": endpoint_id}

    @router.post(
        "/api/system/nodes/assistant/actor-assertions",
        response_model=AssistantActorAssertionIssueResponse,
    )
    async def issue_actor_assertion(
        body: AssistantActorAssertionIssueRequest,
        x_node_id: str | None = Header(default=None),
        x_node_trust_token: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
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
        bearer_parts = str(authorization or "").strip().split(" ", 1)
        if len(bearer_parts) != 2 or bearer_parts[0].lower() != "bearer" or not bearer_parts[1].strip():
            raise HTTPException(status_code=401, detail="assistant_service_authorization_required")
        if service_token_keys is None:
            raise HTTPException(status_code=503, detail="assistant_authorization_unavailable")
        try:
            _, payload = verify_hs256(bearer_parts[1].strip(), await service_token_keys.verification_keys())
            caller_authorization = validate_claims(
                payload,
                audience=body.audience,
                expected_issuer="hexe-core",
                allowed_token_uses={"node_service"},
            )
        except ServiceTokenError as exc:
            raise HTTPException(status_code=403, detail=f"assistant_service_authorization_{str(exc)}") from exc
        if caller_authorization.sub != caller_node_id:
            raise HTTPException(status_code=403, detail="assistant_service_authorization_subject_mismatch")
        if any(scope not in set(caller_authorization.scp) for scope in clean_scopes):
            raise HTTPException(status_code=403, detail="assistant_service_authorization_scope_insufficient")

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
        return AssistantActorAssertionIssueResponse(token=token, claims=claims, grant_id=caller_authorization.authorization_id)

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

    @router.post("/api/system/nodes/assistant/intent-executions/authorize", response_model=IntentExecutionAuthorizeResponse)
    async def authorize_intent_execution(
        body: IntentExecutionAuthorizeRequest,
        x_node_id: str | None = Header(default=None),
        x_node_trust_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        interaction_node_id = str(x_node_id or "").strip()
        registration = require_trusted_node(interaction_node_id, x_node_trust_token)
        if str(getattr(registration, "node_type", "") or "").strip().lower().removesuffix("-node") != "interaction":
            raise HTTPException(status_code=403, detail="intent_execution_interaction_required")
        if body.interaction_audience != f"node-service:{interaction_node_id}:interaction.assistant.turn":
            raise HTTPException(status_code=403, detail="intent_execution_interaction_audience_invalid")
        owner_parts = body.owner_audience.split(":", 2)
        if len(owner_parts) != 3 or owner_parts[0] != "node-service" or not owner_parts[1] or not owner_parts[2]:
            raise HTTPException(status_code=403, detail="intent_execution_owner_audience_invalid")
        if owner_parts[2] != body.target_capability:
            raise HTTPException(status_code=403, detail="intent_execution_target_capability_mismatch")
        owner = registrations.get(owner_parts[1]) if registrations is not None else None
        if owner is None or str(getattr(owner, "trust_status", "") or "").lower() != "trusted":
            raise HTTPException(status_code=403, detail="intent_execution_owner_untrusted")
        try:
            actor_claims = await service.introspect(
                body.actor_assertion,
                audience=body.interaction_audience,
                issuer=issuer,
                requester_node_id=body.requester_node_id,
                conversation_id=body.conversation_id,
                turn_id=body.turn_id,
                required_scopes=["assistant.turn.submit"],
            )
            actor = actor_claims.get("actor") if isinstance(actor_claims.get("actor"), dict) else {}
            identity_state = str(actor.get("identity_state") or "unknown")
            effective_scopes = sorted({str(item).strip() for item in body.required_scopes if str(item).strip()})
            admin_required = body.risk == "admin" or any(scope.startswith("admin.") or ".admin" in scope for scope in effective_scopes)
            if admin_required:
                user_id = str(actor.get("user_id") or "")
                if not user_id and family is not None and actor.get("person_id"):
                    snapshot = await family.snapshot()
                    link = next((item for item in snapshot.get("user_links", []) if item.get("person_id") == actor.get("person_id")), None)
                    user_id = str((link or {}).get("user_id") or "")
                user = await users.get_user_by_id(user_id) if users is not None and user_id else None
                if identity_state != "verified" or user is None or not bool(user.get("enabled")) or str(user.get("role") or "") not in {"owner", "admin"}:
                    raise AssistantAssertionError("intent_execution_admin_scope_required")
            reference, record = await service.issue_intent_execution_reference(
                actor_claims=actor_claims, owner_node_id=owner_parts[1], owner_audience=body.owner_audience,
                intent_id=body.intent_id, contract_version=body.contract_version,
                intent_revision=body.intent_revision, action=body.action,
                target_capability=body.target_capability,
                canonical_arguments_hash=body.canonical_arguments_hash,
                correlation_id=body.correlation_id, required_scopes=body.required_scopes,
                effective_scopes=effective_scopes,
            )
        except AssistantAssertionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return {"ok": True, "contract_version": "assistant.intent-execution-authorization.v1", "authorization_ref": reference, "owner_audience": body.owner_audience, "expires_at": record["expires_at"]}

    @router.post(
        "/api/system/nodes/assistant/intent-executions/introspect",
        response_model=IntentExecutionIntrospectionResponse,
        response_model_exclude_none=True,
        response_model_exclude_defaults=True,
    )
    async def introspect_intent_execution(
        body: IntentExecutionIntrospectRequest,
        x_node_id: str | None = Header(default=None),
        x_node_trust_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        owner_node_id = str(x_node_id or "").strip()
        require_trusted_node(owner_node_id, x_node_trust_token)
        bindings = body.model_dump(exclude={"authorization_ref", "consume"})
        try:
            record = await service.introspect_intent_execution_reference(body.authorization_ref, owner_node_id=owner_node_id, bindings=bindings, consume=body.consume)
        except AssistantAssertionError as exc:
            return {"active": False, "error_code": str(exc)}
        return {"active": True, "actor_id": record["actor_id"], "identity_state": record["identity_state"], "effective_scopes": record["effective_scopes"], "expires_at": record["expires_at"], "replayed": record["replayed"]}

    @router.get("/api/system/nodes/assistant/speaker-enrollment/people", response_model=SpeakerEnrollmentDirectoryResponse)
    async def list_speaker_enrollment_people(
        endpoint_id: str,
        enrollment_session_id: str,
        cursor: int = 0,
        limit: int = 50,
        x_node_id: str | None = Header(default=None),
        x_node_trust_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        node_id = str(x_node_id or "").strip()
        require_trusted_node(node_id, x_node_trust_token)
        require_voice_enrollment_access(node_id, endpoint_id)
        snapshot = await family.snapshot() if family is not None else {}
        assignment = next((item for item in snapshot.get("endpoint_assignments", []) if item.get("endpoint_id") == endpoint_id), None)
        if assignment is None:
            raise HTTPException(status_code=403, detail="speaker_enrollment_endpoint_not_authorized")
        household_id = str(assignment.get("household_id") or "")
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        eligible = []
        for person in snapshot.get("people", []):
            if person.get("status") != "active" or person.get("household_id") != household_id:
                continue
            consents = [item for item in snapshot.get("consents", []) if item.get("person_id") == person.get("person_id") and item.get("purpose") == "speaker-recognition" and item.get("status") == "active"]
            live = [item for item in consents if not item.get("expires_at") or __import__("datetime").datetime.fromisoformat(str(item["expires_at"]).replace("Z", "+00:00")) > now]
            granted = any(item.get("decision") == "granted" for item in live) and not any(item.get("decision") == "denied" for item in live)
            if granted:
                eligible.append({"person_id": person["person_id"], "enrollment_label": person["display_name"], "consent_state": "granted", "eligibility_state": "eligible", "enrollment_status": "available", "reason": None})
        selected = eligible[max(cursor, 0):max(cursor, 0) + min(max(limit, 1), 100)]
        next_cursor = cursor + len(selected) if cursor + len(selected) < len(eligible) else None
        return {"ok": True, "contract_version": "voice.speaker-enrollment.v1", "household_id": household_id, "enrollment_session_id": enrollment_session_id, "items": selected, "next_cursor": next_cursor}

    @router.post("/api/system/nodes/assistant/speaker-enrollment/grants", response_model=SpeakerEnrollmentGrantResponse)
    async def issue_speaker_enrollment_grant(
        body: SpeakerEnrollmentGrantRequest,
        x_node_id: str | None = Header(default=None),
        x_node_trust_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        node_id = str(x_node_id or "").strip()
        require_trusted_node(node_id, x_node_trust_token)
        require_voice_enrollment_access(node_id, body.endpoint_id, scope="assistant.speaker_enrollment.write")
        snapshot = await family.snapshot() if family is not None else {}
        assignment = next((item for item in snapshot.get("endpoint_assignments", []) if item.get("endpoint_id") == body.endpoint_id), None)
        person = next((item for item in snapshot.get("people", []) if item.get("person_id") == body.person_id and item.get("status") == "active"), None)
        if assignment is None or person is None or person.get("household_id") != assignment.get("household_id"):
            raise HTTPException(status_code=403, detail="speaker_enrollment_person_not_eligible")
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        consents = [item for item in snapshot.get("consents", []) if item.get("person_id") == body.person_id and item.get("purpose") == "speaker-recognition" and item.get("status") == "active"]
        live_consents = [item for item in consents if not item.get("expires_at") or __import__("datetime").datetime.fromisoformat(str(item["expires_at"]).replace("Z", "+00:00")) > now]
        if not any(item.get("decision") == "granted" for item in live_consents) or any(item.get("decision") == "denied" for item in live_consents):
            raise HTTPException(status_code=403, detail="speaker_enrollment_consent_required")
        reference, record = await service.issue_speaker_enrollment_grant(node_id=node_id, person_id=body.person_id, household_id=str(person["household_id"]), endpoint_id=body.endpoint_id, enrollment_session_id=body.enrollment_session_id)
        return {"ok": True, "contract_version": "voice.speaker-enrollment.v1", "grant_ref": reference, "expires_at": record["expires_at"], "purpose": record["purpose"]}

    @router.post("/api/system/nodes/assistant/speaker-enrollment/grants/consume")
    async def consume_speaker_enrollment_grant(
        body: SpeakerEnrollmentGrantConsumeRequest,
        x_node_id: str | None = Header(default=None),
        x_node_trust_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        node_id = str(x_node_id or "").strip()
        require_trusted_node(node_id, x_node_trust_token)
        snapshot = await family.snapshot() if family is not None else {}
        assignment = next((item for item in snapshot.get("endpoint_assignments", []) if item.get("endpoint_id") == body.endpoint_id), None)
        person = next((item for item in snapshot.get("people", []) if item.get("person_id") == body.person_id and item.get("status") == "active"), None)
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        consents = [item for item in snapshot.get("consents", []) if item.get("person_id") == body.person_id and item.get("purpose") == "speaker-recognition" and item.get("status") == "active"]
        live_consents = [item for item in consents if not item.get("expires_at") or __import__("datetime").datetime.fromisoformat(str(item["expires_at"]).replace("Z", "+00:00")) > now]
        if assignment is None or person is None or person.get("household_id") != assignment.get("household_id") or not any(item.get("decision") == "granted" for item in live_consents) or any(item.get("decision") == "denied" for item in live_consents):
            return {"active": False, "error_code": "speaker_enrollment_authority_revoked"}
        try:
            record = await service.consume_speaker_enrollment_grant(body.grant_ref, bindings={"node_id": node_id, "person_id": body.person_id, "endpoint_id": body.endpoint_id, "enrollment_session_id": body.enrollment_session_id})
        except AssistantAssertionError as exc:
            return {"active": False, "error_code": str(exc)}
        return {"active": True, "person_id": record["person_id"], "purpose": record["purpose"], "expires_at": record["expires_at"]}

    @router.get("/api/system/nodes/assistant/speaker-enrollment/bindings/{person_id}/status")
    async def speaker_enrollment_binding_status(
        person_id: str,
        endpoint_id: str,
        x_node_id: str | None = Header(default=None),
        x_node_trust_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        node_id = str(x_node_id or "").strip()
        require_trusted_node(node_id, x_node_trust_token)
        require_voice_enrollment_access(node_id, endpoint_id)
        snapshot = await family.snapshot() if family is not None else {}
        assignment = next((item for item in snapshot.get("endpoint_assignments", []) if item.get("endpoint_id") == endpoint_id), None)
        person = next((item for item in snapshot.get("people", []) if item.get("person_id") == person_id), None)
        reason = None
        if assignment is None or person is None or person.get("household_id") != assignment.get("household_id"):
            reason = "household_or_person_removed"
        elif person.get("status") != "active":
            reason = "person_archived"
        else:
            consents = [item for item in snapshot.get("consents", []) if item.get("person_id") == person_id and item.get("purpose") == "speaker-recognition" and item.get("status") == "active"]
            now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            live_consents = [item for item in consents if not item.get("expires_at") or __import__("datetime").datetime.fromisoformat(str(item["expires_at"]).replace("Z", "+00:00")) > now]
            if not any(item.get("decision") == "granted" for item in live_consents) or any(item.get("decision") == "denied" for item in live_consents):
                reason = "consent_not_granted"
        return {"active": reason is None, "person_id": person_id, "reason": reason}

    return router
