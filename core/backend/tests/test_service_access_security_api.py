import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.system.auth import ServiceTokenKeyStore, sign_hs256
from app.system.onboarding import NodeRegistrationsStore, NodeTrustIssuanceService, NodeTrustStore
from app.system.onboarding.registrations import NodeRegistrationRecord
from app.system.service_access import ServiceAccessGrantStore, build_service_access_router


class _FakeSettingsStore:
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    async def get(self, key: str):
        return self._data.get(key)

    async def set(self, key: str, value):
        self._data[key] = value


def _registration(node_id: str) -> NodeRegistrationRecord:
    now = "2026-09-27T00:00:00+00:00"
    return NodeRegistrationRecord(
        node_id=node_id,
        node_type="ai-node",
        node_name=node_id,
        node_software_version="1.0.0",
        requested_node_type="ai-node",
        capabilities_summary=[],
        trust_status="trusted",
        source_onboarding_session_id=f"session-{node_id}",
        approved_by_user_id="admin",
        approved_at=now,
        created_at=now,
        updated_at=now,
    )


class TestServiceAccessSecurityApi:
    def setup_method(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self.settings = _FakeSettingsStore()
        self.keys = ServiceTokenKeyStore(self.settings)
        self.trust_store = NodeTrustStore(path=base / "trust.json")
        self.trust = NodeTrustIssuanceService(self.trust_store)
        self.registrations = NodeRegistrationsStore(path=base / "registrations.json")
        self.grants = ServiceAccessGrantStore(base / "service_access_grants.json")
        self.caller_id, self.caller_token = self._trusted_node("node-caller")
        self.provider_id, self.provider_token = self._trusted_node("node-ai-provider")
        self.audience = f"node-service:{self.provider_id}:openai"
        self.env = patch.dict(os.environ, {"HEXE_ADMIN_TOKEN": "admin-test-token"}, clear=False)
        self.env.start()
        app = FastAPI()
        app.include_router(
            build_service_access_router(
                key_store=self.keys,
                grant_store=self.grants,
                trust=self.trust,
                registrations=self.registrations,
                core_id="core-primary",
            ),
            prefix="/api",
        )
        self.client = TestClient(app)

    def teardown_method(self) -> None:
        self.env.stop()
        self.tmpdir.cleanup()

    def _trusted_node(self, node_id: str) -> tuple[str, str]:
        issued = self.trust.reissue_for_node(
            node_id=node_id,
            node_type="ai-node",
            source_session_id=f"session-{node_id}",
        )["activation"]
        self.registrations.upsert(_registration(node_id))
        return node_id, str(issued["node_trust_token"])

    def _create_grant(self, scopes: list[str] | None = None) -> dict:
        response = self.client.post(
            "/api/system/nodes/service-access/grants",
            headers={"X-Admin-Token": "admin-test-token"},
            json={
                "subject_node_id": self.caller_id,
                "audience": self.audience,
                "scopes": scopes or ["ai.prompts.read", "ai.prompts.write"],
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["grant"]

    def _authorize(self, scopes: list[str] | None = None) -> dict:
        response = self.client.post(
            "/api/system/nodes/service-access/authorize",
            headers={"X-Node-Trust-Token": self.caller_token},
            json={
                "node_id": self.caller_id,
                "service_id": self.audience,
                "requested_scopes": scopes or ["ai.prompts.read"],
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    def _introspect(self, token: str, **body) -> object:
        return self.client.post(
            "/api/system/nodes/services/introspect",
            headers={"X-Node-Id": self.provider_id, "X-Node-Trust-Token": self.provider_token},
            json={"token": token, **body},
        )

    def test_governed_access_issuance_and_valid_introspection(self) -> None:
        grant = self._create_grant()
        issued = self._authorize()

        assert issued["claims"]["iss"] == "hexe-core"
        assert issued["claims"]["token_use"] == "node_service_access"
        assert issued["claims"]["authorization_id"] == grant["grant_id"]
        response = self._introspect(
            issued["token"],
            expected_audience=self.audience,
            required_scopes=["ai.prompts.read"],
        )

        assert response.status_code == 200, response.text
        assert response.json()["active"] is True
        assert response.json()["claims"]["sub"] == self.caller_id
        assert response.json()["claims"]["aud"] == self.audience

    def test_introspection_requires_current_provider_trust(self) -> None:
        self._create_grant()
        token = self._authorize()["token"]

        missing = self.client.post("/api/system/nodes/services/introspect", json={"token": token})
        assert missing.status_code == 401
        assert missing.json()["detail"] == "node_identity_required"

        invalid = self.client.post(
            "/api/system/nodes/services/introspect",
            headers={"X-Node-Id": self.provider_id, "X-Node-Trust-Token": "invalid"},
            json={"token": token},
        )
        assert invalid.status_code == 403
        assert invalid.json()["detail"] == "untrusted_node"

    def test_stable_inactive_token_failures(self) -> None:
        self._create_grant()
        token = self._authorize()["token"]

        malformed = self._introspect("not-a-jwt")
        assert malformed.json() == {"active": False, "claims": None, "error_code": "token_malformed"}

        header, payload, signature = token.split(".")
        signature = ("A" if signature[0] != "A" else "B") + signature[1:]
        invalid_signature = self._introspect(f"{header}.{payload}.{signature}")
        assert invalid_signature.json()["error_code"] == "token_signature_invalid"

        audience = self._introspect(token, expected_audience=f"{self.audience}-wrong")
        assert audience.json()["error_code"] == "token_audience_mismatch"

        scope = self._introspect(token, required_scopes=["ai.prompts.lifecycle"])
        assert scope.json()["error_code"] == "token_scope_insufficient"

    def test_expired_token_and_foreign_audience(self) -> None:
        key = asyncio.run(self.keys.active_key())
        now = int(time.time())
        base_claims = {
            "iss": "hexe-core",
            "token_use": "node_service",
            "authorization_id": "authz-test",
            "sub": self.caller_id,
            "aud": self.audience,
            "scp": ["service.execute:task.image_generation"],
            "iat": now - 120,
            "exp": now - 60,
            "jti": "expired-token",
        }
        expired = sign_hs256({"alg": "HS256", "typ": "JWT", "kid": key["kid"]}, base_claims, str(key["secret"]))
        response = self._introspect(expired)
        assert response.json()["error_code"] == "token_expired"

        foreign_claims = {**base_claims, "aud": "node-service:another-provider:openai", "exp": now + 60, "jti": "foreign-token"}
        foreign = sign_hs256({"alg": "HS256", "typ": "JWT", "kid": key["kid"]}, foreign_claims, str(key["secret"]))
        denied = self._introspect(foreign)
        assert denied.status_code == 403
        assert denied.json()["detail"] == "service_token_audience_not_owned"

    def test_previous_rotation_key_remains_valid(self) -> None:
        self._create_grant()
        issued = self._authorize()
        asyncio.run(self.keys.rotate())

        response = self._introspect(issued["token"], required_scopes=["ai.prompts.read"])
        assert response.status_code == 200
        assert response.json()["active"] is True

        ring = self.settings._data["auth.service_token.keys"]
        assert isinstance(ring, list)
        retired = next(item for item in ring if not item["active"])
        assert retired["verify_until"] >= issued["claims"]["exp"] + 30

    def test_rotation_gives_legacy_active_key_a_retention_floor(self) -> None:
        key = asyncio.run(self.keys.active_key())
        key.pop("max_token_exp", None)
        before = int(time.time())

        ring = asyncio.run(self.keys.rotate())

        retired = next(item for item in ring if item["kid"] == key["kid"])
        assert retired["verify_until"] >= before + 630

    def test_revoked_grant_and_subject_trust_invalidate_token(self) -> None:
        grant = self._create_grant()
        issued = self._authorize()
        revoked = self.client.post(
            f"/api/system/nodes/service-access/grants/{grant['grant_id']}/revoke",
            headers={"X-Admin-Token": "admin-test-token"},
        )
        assert revoked.status_code == 200
        assert self._introspect(issued["token"]).json()["error_code"] == "token_authorization_revoked"

        active_grant = self._create_grant(["ai.jobs.read"])
        assert active_grant["status"] == "active"
        job_token = self._authorize(["ai.jobs.read"])["token"]
        assert self.trust.revoke_node(self.caller_id, reason="test") is True
        assert self._introspect(job_token).json()["error_code"] == "token_subject_untrusted"

    def test_explicitly_granted_core_subject_does_not_require_node_registration(self) -> None:
        grant = self.grants.create(
            subject_node_id="core-primary",
            audience=self.audience,
            scopes=["assistant.turn.submit"],
            expires_at=None,
        )
        key = asyncio.run(self.keys.active_key())
        now = int(time.time())
        claims = {
            "iss": "hexe-core",
            "token_use": "node_service_access",
            "authorization_id": grant.grant_id,
            "provider_node_id": self.provider_id,
            "sub": "core-primary",
            "aud": self.audience,
            "scp": ["assistant.turn.submit"],
            "iat": now,
            "exp": now + 120,
            "jti": "core-assistant-turn",
        }
        token = sign_hs256(
            {"alg": "HS256", "typ": "JWT", "kid": key["kid"]},
            claims,
            str(key["secret"]),
        )

        response = self._introspect(
            token,
            expected_audience=self.audience,
            required_scopes=["assistant.turn.submit"],
        )

        assert response.status_code == 200, response.text
        assert response.json()["active"] is True
        assert response.json()["claims"]["sub"] == "core-primary"

    def test_unregistered_non_core_subject_remains_untrusted(self) -> None:
        grant = self.grants.create(
            subject_node_id="unregistered-caller",
            audience=self.audience,
            scopes=["assistant.turn.submit"],
            expires_at=None,
        )
        key = asyncio.run(self.keys.active_key())
        now = int(time.time())
        token = sign_hs256(
            {"alg": "HS256", "typ": "JWT", "kid": key["kid"]},
            {
                "iss": "hexe-core",
                "token_use": "node_service_access",
                "authorization_id": grant.grant_id,
                "provider_node_id": self.provider_id,
                "sub": "unregistered-caller",
                "aud": self.audience,
                "scp": ["assistant.turn.submit"],
                "iat": now,
                "exp": now + 120,
                "jti": "unregistered-assistant-turn",
            },
            str(key["secret"]),
        )

        response = self._introspect(token)

        assert response.status_code == 200, response.text
        assert response.json()["error_code"] == "token_subject_untrusted"

    def test_management_scope_requires_explicit_grant(self) -> None:
        denied = self.client.post(
            "/api/system/nodes/service-access/authorize",
            headers={"X-Node-Trust-Token": self.caller_token},
            json={
                "node_id": self.caller_id,
                "service_id": self.audience,
                "requested_scopes": ["ai.jobs.cancel"],
            },
        )
        assert denied.status_code == 403
        assert denied.json()["detail"] == "service_access_not_authorized"

        unsupported = self.client.post(
            "/api/system/nodes/service-access/grants",
            headers={"X-Admin-Token": "admin-test-token"},
            json={"subject_node_id": self.caller_id, "audience": self.audience, "scopes": ["admin.everything"]},
        )
        assert unsupported.status_code == 422

        assistant = self.client.post(
            "/api/system/nodes/service-access/grants",
            headers={"X-Admin-Token": "admin-test-token"},
            json={
                "subject_node_id": self.caller_id,
                "audience": "node-service:node-interaction-1:interaction.assistant.turn",
                "scopes": ["assistant.turn.submit", "assistant.turn.cancel"],
            },
        )
        assert assistant.status_code == 200
        assert assistant.json()["grant"]["scopes"] == ["assistant.turn.cancel", "assistant.turn.submit"]

    def test_admin_can_inspect_and_update_grant(self) -> None:
        grant = self._create_grant(["ai.prompts.read"])
        headers = {"X-Admin-Token": "admin-test-token"}

        fetched = self.client.get(
            f"/api/system/nodes/service-access/grants/{grant['grant_id']}",
            headers=headers,
        )
        assert fetched.status_code == 200
        assert fetched.json()["grant"]["scopes"] == ["ai.prompts.read"]

        updated = self.client.put(
            f"/api/system/nodes/service-access/grants/{grant['grant_id']}",
            headers=headers,
            json={"scopes": ["ai.prompts.read", "ai.prompts.review"], "status": "active"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["grant"]["scopes"] == ["ai.prompts.read", "ai.prompts.review"]

        listed = self.client.get("/api/system/nodes/service-access/grants", headers=headers)
        assert listed.status_code == 200
        assert [item["grant_id"] for item in listed.json()["items"]] == [grant["grant_id"]]

    def test_grants_persist_without_tokens_or_secrets(self) -> None:
        grant = self._create_grant()
        raw = json.loads((Path(self.tmpdir.name) / "service_access_grants.json").read_text(encoding="utf-8"))
        assert raw["grants"][0]["grant_id"] == grant["grant_id"]
        assert "token" not in json.dumps(raw).lower()
        assert "secret" not in json.dumps(raw).lower()
