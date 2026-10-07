from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.system.onboarding.registrations import NodeRegistrationsStore
from app.system.onboarding.trust import NodeTrustIssuanceService

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


def build_assistant_auth_router(
    service: AssistantAssertionService,
    *,
    trust: NodeTrustIssuanceService | None = None,
    registrations: NodeRegistrationsStore | None = None,
    issuer: str = "hexe-core",
) -> APIRouter:
    router = APIRouter(tags=["assistant-authorization"])

    @router.get("/.well-known/hexe-core-jwks.json")
    async def assistant_jwks() -> dict:
        return await service.keys.jwks()

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
        if trust is None or registrations is None:
            raise HTTPException(status_code=503, detail="assistant_introspection_unavailable")
        registration = registrations.get(provider_node_id)
        if trust.authenticate_node(provider_node_id, str(x_node_trust_token)) is None or registration is None:
            raise HTTPException(status_code=403, detail="untrusted_node")
        if str(registration.trust_status or "").strip().lower() != "trusted":
            raise HTTPException(status_code=403, detail="untrusted_node")
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
