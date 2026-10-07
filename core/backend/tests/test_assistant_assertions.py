import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.system.assistant_auth import (
    ASSISTANT_ASSERTION_TTL_SECONDS,
    AssistantAssertionError,
    AssistantAssertionKeyStore,
    AssistantAssertionService,
    verify_assistant_assertion,
    build_assistant_auth_router,
)
from app.system.settings.store import SettingsStore


def test_actor_assertion_round_trip_and_jwks(tmp_path):
    settings = SettingsStore(str(tmp_path / "settings.db"))
    service = AssistantAssertionService(settings)
    token, claims = asyncio.run(
        service.issue_actor_assertion(
            core_id="core-1",
            audience="interaction-assistant-1",
            requester_node_id="node-voice-1",
            conversation_id="conv-1",
            turn_id="turn-1",
            actor_kind="person",
            identity_state="probable",
            scopes=["timer.create", "assistant.turn.submit", "timer.create"],
            person_id="person-1",
            household_id="household-1",
            endpoint_id="endpoint-kitchen",
            room_id="kitchen",
            confidence=0.83,
            now=1000,
        )
    )
    jwks = asyncio.run(service.keys.jwks(now=1000))

    verified = verify_assistant_assertion(
        token,
        jwks=jwks,
        audience="interaction-assistant-1",
        issuer="core-1",
        requester_node_id="node-voice-1",
        conversation_id="conv-1",
        turn_id="turn-1",
        required_scopes=["assistant.turn.submit"],
        now=1001,
    )

    assert verified == claims
    assert claims["sub"] == "actor:person:person-1"
    assert claims["exp"] - claims["iat"] == ASSISTANT_ASSERTION_TTL_SECONDS
    assert claims["scope"] == ["assistant.turn.submit", "timer.create"]
    assert set(jwks["keys"][0]) == {"kty", "crv", "use", "alg", "kid", "x"}
    assert "private_key" not in str(jwks)


def test_actor_assertion_rejects_wrong_binding_and_expiry(tmp_path):
    settings = SettingsStore(str(tmp_path / "settings.db"))
    service = AssistantAssertionService(settings)
    token, _ = asyncio.run(
        service.issue_actor_assertion(
            core_id="core-1",
            audience="interaction-assistant-1",
            requester_node_id="node-core-1",
            conversation_id="conv-1",
            turn_id="turn-1",
            actor_kind="human_user",
            identity_state="verified",
            scopes=["assistant.turn.submit"],
            user_id="user-1",
            device_id="device-1",
            now=2000,
        )
    )
    jwks = asyncio.run(service.keys.jwks(now=2000))

    with pytest.raises(AssistantAssertionError, match="actor_assertion_binding_invalid"):
        verify_assistant_assertion(
            token,
            jwks=jwks,
            audience="interaction-assistant-other",
            issuer="core-1",
            requester_node_id="node-core-1",
            conversation_id="conv-1",
            turn_id="turn-1",
            now=2001,
        )
    with pytest.raises(AssistantAssertionError, match="actor_assertion_expired"):
        verify_assistant_assertion(
            token,
            jwks=jwks,
            audience="interaction-assistant-1",
            issuer="core-1",
            requester_node_id="node-core-1",
            conversation_id="conv-1",
            turn_id="turn-1",
            now=2060,
        )


def test_actor_identity_rules_and_authorization_epochs(tmp_path):
    settings = SettingsStore(str(tmp_path / "settings.db"))
    service = AssistantAssertionService(settings)

    with pytest.raises(AssistantAssertionError, match="verified_user_required"):
        asyncio.run(
            service.issue_actor_assertion(
                core_id="core-1",
                audience="interaction-assistant-1",
                requester_node_id="node-core-1",
                conversation_id="conv-1",
                turn_id="turn-1",
                actor_kind="human_user",
                identity_state="probable",
                scopes=["assistant.turn.submit"],
                user_id="user-1",
            )
        )

    assert asyncio.run(service.bump_authorization_epoch(kind="user", identifier="user-1")) == 1
    assert asyncio.run(service.bump_authorization_epoch(kind="node", identifier="node-core-1")) == 1
    _, claims = asyncio.run(
        service.issue_actor_assertion(
            core_id="core-1",
            audience="interaction-assistant-1",
            requester_node_id="node-core-1",
            conversation_id="conv-2",
            turn_id="turn-2",
            actor_kind="human_user",
            identity_state="verified",
            scopes=["assistant.turn.submit"],
            user_id="user-1",
            now=3000,
        )
    )
    assert claims["authorization_epochs"]["user"] == 1
    assert claims["authorization_epochs"]["node"] == 1


def test_rotation_keeps_previous_public_key_until_assertion_expiry(tmp_path):
    settings = SettingsStore(str(tmp_path / "settings.db"))
    keys = AssistantAssertionKeyStore(settings)
    service = AssistantAssertionService(settings, keys)
    token, _ = asyncio.run(
        service.issue_actor_assertion(
            core_id="core-1",
            audience="interaction-assistant-1",
            requester_node_id="node-core-1",
            conversation_id="conv-1",
            turn_id="turn-1",
            actor_kind="anonymous",
            identity_state="unknown",
            scopes=["assistant.turn.submit"],
            now=4000,
        )
    )
    original_kid = token.split(".")[0]
    asyncio.run(keys.rotate(now=4001))
    jwks = asyncio.run(keys.jwks(now=4001))

    assert len(jwks["keys"]) == 2
    verify_assistant_assertion(
        token,
        jwks=jwks,
        audience="interaction-assistant-1",
        issuer="core-1",
        requester_node_id="node-core-1",
        conversation_id="conv-1",
        turn_id="turn-1",
        now=4002,
    )
    assert original_kid


def test_public_jwks_route_exposes_only_verification_material(tmp_path):
    settings = SettingsStore(str(tmp_path / "settings.db"))
    service = AssistantAssertionService(settings)
    app = FastAPI()
    app.include_router(build_assistant_auth_router(service))

    response = TestClient(app).get("/.well-known/hexe-core-jwks.json")

    assert response.status_code == 200
    assert len(response.json()["keys"]) == 1
    assert response.json()["keys"][0]["alg"] == "EdDSA"
    assert "private_key" not in response.text


def test_introspection_rechecks_epochs_and_consumes_approval_once(tmp_path):
    settings = SettingsStore(str(tmp_path / "settings.db"))
    service = AssistantAssertionService(settings)
    actor_token, actor_claims = asyncio.run(
        service.issue_actor_assertion(
            core_id="core-1",
            audience="interaction-assistant-1",
            requester_node_id="node-core-1",
            conversation_id="conv-1",
            turn_id="turn-1",
            actor_kind="human_user",
            identity_state="verified",
            scopes=["assistant.turn.resume", "timer.create"],
            user_id="user-1",
            device_id="device-1",
            now=5000,
        )
    )
    assert asyncio.run(
        service.introspect(
            actor_token,
            audience="interaction-assistant-1",
            issuer="core-1",
            requester_node_id="node-core-1",
            conversation_id="conv-1",
            turn_id="turn-1",
            required_scopes=["timer.create"],
            now=5001,
        )
    )["sub"] == "actor:user:user-1"

    approval_token, _ = asyncio.run(
        service.issue_approval_assertion(
            actor_claims=actor_claims,
            approval_id="approval-1",
            action="timer.create",
            intent_id="timer.create",
            intent_revision="1",
            canonical_arguments_hash="a" * 64,
            target_capability="interaction.timer.create",
            correlation_id="correlation-1",
            now=5002,
        )
    )
    kwargs = dict(
        audience="interaction-assistant-1",
        issuer="core-1",
        requester_node_id="node-core-1",
        conversation_id="conv-1",
        turn_id="turn-1",
        required_scopes=["assistant.turn.resume"],
        consume_approval=True,
        now=5003,
    )
    assert asyncio.run(service.introspect(approval_token, **kwargs))["approval"]["approval_id"] == "approval-1"
    with pytest.raises(AssistantAssertionError, match="approval_assertion_replayed"):
        asyncio.run(service.introspect(approval_token, **kwargs))

    asyncio.run(service.bump_authorization_epoch(kind="user", identifier="user-1"))
    with pytest.raises(AssistantAssertionError, match="actor_assertion_revoked"):
        asyncio.run(
            service.introspect(
                actor_token,
                audience="interaction-assistant-1",
                issuer="core-1",
                requester_node_id="node-core-1",
                conversation_id="conv-1",
                turn_id="turn-1",
                now=5004,
            )
        )


def test_provider_introspection_endpoint_authenticates_owner_and_returns_stable_inactive(tmp_path):
    settings = SettingsStore(str(tmp_path / "settings.db"))
    service = AssistantAssertionService(settings)
    audience = "node-service:node-interaction-1:interaction.assistant.turn"
    token, _ = asyncio.run(
        service.issue_actor_assertion(
            core_id="core-1",
            audience=audience,
            requester_node_id="node-voice-1",
            conversation_id="conv-1",
            turn_id="turn-1",
            actor_kind="anonymous",
            identity_state="unknown",
            scopes=["assistant.turn.submit"],
            now=int(__import__("time").time()),
        )
    )

    class Trust:
        def authenticate_node(self, node_id, token_value):
            return object() if node_id == "node-interaction-1" and token_value == "trusted" else None

    class Registration:
        trust_status = "trusted"

    class Registrations:
        def get(self, node_id):
            return Registration() if node_id == "node-interaction-1" else None

    app = FastAPI()
    app.include_router(
        build_assistant_auth_router(
            service,
            trust=Trust(),
            registrations=Registrations(),
            issuer="core-1",
        )
    )
    client = TestClient(app)
    body = {
        "token": token,
        "expected_audience": audience,
        "requester_node_id": "node-voice-1",
        "conversation_id": "conv-1",
        "turn_id": "turn-1",
        "required_scopes": ["assistant.turn.submit"],
    }

    active = client.post(
        "/api/system/nodes/assistant/assertions/introspect",
        json=body,
        headers={"X-Node-Id": "node-interaction-1", "X-Node-Trust-Token": "trusted"},
    )
    wrong_turn = client.post(
        "/api/system/nodes/assistant/assertions/introspect",
        json={**body, "turn_id": "turn-other"},
        headers={"X-Node-Id": "node-interaction-1", "X-Node-Trust-Token": "trusted"},
    )
    foreign = client.post(
        "/api/system/nodes/assistant/assertions/introspect",
        json={**body, "expected_audience": "node-service:node-other:interaction.assistant.turn"},
        headers={"X-Node-Id": "node-interaction-1", "X-Node-Trust-Token": "trusted"},
    )

    assert active.status_code == 200
    assert active.json()["active"] is True
    assert active.json()["claims"]["sub"].startswith("actor:anonymous:")
    assert wrong_turn.status_code == 200
    assert wrong_turn.json() == {"active": False, "error_code": "actor_assertion_binding_invalid", "claims": None}
    assert foreign.status_code == 403
    assert foreign.json()["detail"] == "assistant_assertion_audience_not_owned"
