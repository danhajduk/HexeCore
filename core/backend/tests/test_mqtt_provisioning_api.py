import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.addons.models import AddonMeta, BackendAddon, RegisteredAddon
from app.addons.registry import AddonRegistry
from app.system.auth import ServiceTokenKeyStore, sign_hs256
from app.system.mqtt import MqttCredentialStore, MqttIntegrationStateStore, MqttNodeBridgeGrant, build_mqtt_router
from app.system.onboarding import NodeRegistrationRecord, NodeRegistrationsStore, NodeTrustIssuanceService, NodeTrustStore


class _FakeSettingsStore:
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    async def get(self, key: str):
        return self._data.get(key)

    async def set(self, key: str, value):
        self._data[key] = value
        return value


class _FakeMqttManager:
    async def status(self):
        return {"ok": True}

    async def restart(self):
        return None

    async def publish_test(self, topic: str | None = None, payload: dict | None = None):
        return {"ok": True, "topic": topic or "hexe/core/mqtt/info", "payload": payload or {}}


class TestMqttProvisioningApi(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(os.environ, {"HEXE_ADMIN_TOKEN": "test-token"}, clear=False)
        self.env_patch.start()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.settings = _FakeSettingsStore()
        self.key_store = ServiceTokenKeyStore(self.settings)
        self.state_store = MqttIntegrationStateStore(str(Path(self.tmpdir.name) / "mqtt_state.json"))
        self.credential_store = MqttCredentialStore(str(Path(self.tmpdir.name) / "mqtt_credentials.json"))
        self.node_registrations = NodeRegistrationsStore(path=Path(self.tmpdir.name) / "node_registrations.json")
        self.node_trust = NodeTrustIssuanceService(NodeTrustStore(path=Path(self.tmpdir.name) / "node_trust.json"))
        self.registry = AddonRegistry(
            addons={
                "vision": BackendAddon(
                    meta=AddonMeta(id="vision", name="Vision", version="1.0.0"),
                    router=APIRouter(),
                )
            },
            errors={},
            enabled={"vision": True},
            registered={
                "mqtt": RegisteredAddon(
                    id="mqtt",
                    name="MQTT",
                    version="1.0.0",
                    base_url="http://mqtt-addon.local:9100",
                )
            },
        )
        app = FastAPI()
        app.include_router(
            build_mqtt_router(
                _FakeMqttManager(),
                self.registry,
                self.state_store,
                self.key_store,
                credential_store=self.credential_store,
                node_registrations_store=self.node_registrations,
                node_trust_issuance=self.node_trust,
            ),
            prefix="/api/system",
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        self.env_patch.stop()

    def _token(self, *, sub: str, scopes: list[str]) -> str:
        key = asyncio.run(self.key_store.active_key())
        now = int(time.time())
        return sign_hs256(
            {"alg": "HS256", "typ": "JWT", "kid": key["kid"]},
            {
                "sub": sub,
                "aud": "hexe-core",
                "scp": scopes,
                "exp": now + 600,
                "iat": now,
                "jti": f"jti-{now}",
            },
            key["secret"],
        )

    def _trusted_node(self, node_id: str = "node-6812313e6d1efad6") -> str:
        now = "2026-06-25T00:00:00+00:00"
        self.node_registrations.upsert(
            NodeRegistrationRecord(
                node_id=node_id,
                node_type="interaction-node",
                node_name="hexe-interaction",
                node_software_version="0.1.0",
                requested_node_type="interaction-node",
                capabilities_summary=[],
                trust_status="trusted",
                source_onboarding_session_id="session-1",
                approved_by_user_id="admin",
                approved_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        activation = self.node_trust.reissue_for_node(
            node_id=node_id,
            node_type="interaction-node",
            source_session_id="session-1",
        )
        return str(activation["activation"]["node_trust_token"])

    def _mark_mqtt_setup_ready(self) -> None:
        setup_ready = self.client.post(
            "/api/system/mqtt/setup-state",
            headers={"X-Admin-Token": "test-token"},
            json={
                "requires_setup": True,
                "setup_complete": True,
                "setup_status": "ready",
                "broker_mode": "embedded",
                "direct_mqtt_supported": True,
                "authority_ready": True,
            },
        )
        self.assertEqual(setup_ready.status_code, 200, setup_ready.text)

    def _request_homeassistant_bridge_grant(
        self,
        *,
        node_id: str = "node-6812313e6d1efad6",
        token: str | None = None,
    ) -> dict:
        token = token or self._trusted_node(node_id)
        requested = self.client.post(
            "/api/system/mqtt/node-bridge-grants/request",
            headers={
                "X-Node-Id": node_id,
                "X-Node-Trust-Token": token,
            },
            json={
                "node_id": node_id,
                "bridge_id": "homeassistant",
                "bridge_type": "homeassistant",
                "publish_topics": [
                    "homeassistant/+/hexe_ecosystem/+/config",
                    "homeassistant/hexe_ecosystem/state",
                ],
                "subscribe_topics": ["homeassistant/status"],
            },
        )
        self.assertEqual(requested.status_code, 200, requested.text)
        return requested.json()["grant"]

    def _approve_homeassistant_bridge_grant(self, node_id: str = "node-6812313e6d1efad6") -> dict:
        approved = self.client.post(
            f"/api/system/mqtt/node-bridge-grants/{node_id}:homeassistant/approve",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["grant"]["status"], "approved")
        return approved.json()["grant"]

    def test_provisioning_and_revocation_handshake(self) -> None:
        setup_ready = self.client.post(
            "/api/system/mqtt/setup-state",
            headers={"X-Admin-Token": "test-token"},
            json={
                "requires_setup": True,
                "setup_complete": True,
                "setup_status": "ready",
                "broker_mode": "embedded",
                "direct_mqtt_supported": True,
                "authority_ready": True,
            },
        )
        self.assertEqual(setup_ready.status_code, 200, setup_ready.text)
        approved = self.client.post(
            "/api/system/mqtt/registrations/approve",
            headers={"X-Admin-Token": "test-token"},
            json={
                "addon_id": "vision",
                "access_mode": "both",
                "publish_topics": ["hexe/addons/vision/event/#"],
                "subscribe_topics": ["hexe/addons/vision/command/#"],
                "capabilities": {"ha_discovery": "gateway_managed"},
            },
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertTrue(approved.json()["ok"])

        provision = self.client.post(
            "/api/system/mqtt/registrations/vision/provision",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(provision.status_code, 200, provision.text)
        self.assertTrue(provision.json()["ok"])
        self.assertEqual(provision.json()["status"], "active")

        revoked = self.client.post(
            "/api/system/mqtt/registrations/vision/revoke",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertTrue(revoked.json()["ok"])
        self.assertEqual(revoked.json()["status"], "revoked")

    def test_node_bridge_grant_request_approval_and_provisioning(self) -> None:
        token = self._trusted_node()
        grant = self._request_homeassistant_bridge_grant(token=token)
        self.assertEqual(grant["grant_id"], "node-6812313e6d1efad6:homeassistant")
        self.assertEqual(grant["status"], "requested")
        self.assertEqual(grant["requester_principal_id"], "node:node-6812313e6d1efad6")

        grants = self.client.get("/api/system/mqtt/node-bridge-grants", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(grants.status_code, 200, grants.text)
        self.assertEqual(grants.json()["items"][0]["bridge_id"], "homeassistant")

        self._approve_homeassistant_bridge_grant()
        self._mark_mqtt_setup_ready()

        provisioned = self.client.post(
            "/api/system/mqtt/node-bridge-grants/node-6812313e6d1efad6:homeassistant/provision",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(provisioned.status_code, 200, provisioned.text)
        body = provisioned.json()
        self.assertEqual(body["grant"]["status"], "active")
        self.assertEqual(body["principal"]["managed_by"], "node_bridge_grant")
        self.assertNotIn("credential", body)

    def test_node_can_claim_own_approved_bridge_credential(self) -> None:
        token = self._trusted_node()
        self._request_homeassistant_bridge_grant(token=token)
        self._approve_homeassistant_bridge_grant()
        self._mark_mqtt_setup_ready()

        claim = self.client.post(
            "/api/system/mqtt/node-bridge-grants/node-6812313e6d1efad6:homeassistant/credential/claim",
            headers={
                "X-Node-Id": "node-6812313e6d1efad6",
                "X-Node-Trust-Token": token,
            },
            json={"bridge_id": "homeassistant"},
        )
        self.assertEqual(claim.status_code, 200, claim.text)
        body = claim.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["grant"]["status"], "active")
        self.assertEqual(body["grant"]["delivery_status"], "delivered")
        self.assertEqual(body["grant"]["credential_claimed_by_node_id"], "node-6812313e6d1efad6")
        self.assertTrue(body["grant"]["credential_claimed_at"])
        self.assertTrue(body["grant"]["last_credential_delivery_at"])
        self.assertTrue(body["mqtt"]["username"].startswith("hb_"))
        self.assertTrue(body["mqtt"]["password"])

        second_claim = self.client.post(
            "/api/system/mqtt/node-bridge-grants/node-6812313e6d1efad6:homeassistant/credential/claim",
            headers={
                "X-Node-Id": "node-6812313e6d1efad6",
                "X-Node-Trust-Token": token,
            },
        )
        self.assertEqual(second_claim.status_code, 200, second_claim.text)
        self.assertEqual(second_claim.json()["mqtt"]["password"], body["mqtt"]["password"])

        grants = self.client.get("/api/system/mqtt/node-bridge-grants", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(grants.status_code, 200, grants.text)
        self.assertNotIn("password", str(grants.json()))
        detail = self.client.get(
            "/api/system/mqtt/node-bridge-grants/node-6812313e6d1efad6:homeassistant",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertNotIn("password", str(detail.json()))

    def test_node_cannot_claim_another_nodes_bridge_credential(self) -> None:
        owner_token = self._trusted_node("node-owner")
        other_token = self._trusted_node("node-other")
        self._request_homeassistant_bridge_grant(node_id="node-owner", token=owner_token)
        self._approve_homeassistant_bridge_grant("node-owner")
        self._mark_mqtt_setup_ready()

        claim = self.client.post(
            "/api/system/mqtt/node-bridge-grants/node-owner:homeassistant/credential/claim",
            headers={"X-Node-Id": "node-other", "X-Node-Trust-Token": other_token},
        )
        self.assertEqual(claim.status_code, 403, claim.text)
        self.assertEqual(claim.json()["detail"]["error"], "node_bridge_grant_node_mismatch")

    def test_node_cannot_claim_bridge_credential_before_approval(self) -> None:
        token = self._trusted_node()
        self._request_homeassistant_bridge_grant(token=token)
        self._mark_mqtt_setup_ready()

        claim = self.client.post(
            "/api/system/mqtt/node-bridge-grants/node-6812313e6d1efad6:homeassistant/credential/claim",
            headers={
                "X-Node-Id": "node-6812313e6d1efad6",
                "X-Node-Trust-Token": token,
            },
        )
        self.assertEqual(claim.status_code, 400, claim.text)
        self.assertEqual(claim.json()["detail"]["error"], "node_bridge_grant_not_approved:requested")

    def test_node_cannot_claim_revoked_or_rejected_bridge_credential(self) -> None:
        token = self._trusted_node()
        self._request_homeassistant_bridge_grant(token=token)
        self._approve_homeassistant_bridge_grant()
        self._mark_mqtt_setup_ready()

        revoked = self.client.post(
            "/api/system/mqtt/node-bridge-grants/node-6812313e6d1efad6:homeassistant/revoke",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)

        claim_revoked = self.client.post(
            "/api/system/mqtt/node-bridge-grants/node-6812313e6d1efad6:homeassistant/credential/claim",
            headers={
                "X-Node-Id": "node-6812313e6d1efad6",
                "X-Node-Trust-Token": token,
            },
        )
        self.assertEqual(claim_revoked.status_code, 400, claim_revoked.text)
        self.assertEqual(claim_revoked.json()["detail"]["error"], "node_bridge_grant_revoked")

        rejected_grant = MqttNodeBridgeGrant(
            grant_id="node-6812313e6d1efad6:rejectedbridge",
            node_id="node-6812313e6d1efad6",
            bridge_id="rejectedbridge",
            bridge_type="test",
            status="rejected",
            requested_publish_topics=["external/test/state"],
            requested_subscribe_topics=[],
            requester_principal_id="node:node-6812313e6d1efad6",
        )
        asyncio.run(self.state_store.upsert_node_bridge_grant(rejected_grant))
        claim_rejected = self.client.post(
            "/api/system/mqtt/node-bridge-grants/node-6812313e6d1efad6:rejectedbridge/credential/claim",
            headers={
                "X-Node-Id": "node-6812313e6d1efad6",
                "X-Node-Trust-Token": token,
            },
        )
        self.assertEqual(claim_rejected.status_code, 400, claim_rejected.text)
        self.assertEqual(claim_rejected.json()["detail"]["error"], "node_bridge_grant_rejected")

    def test_grant_and_setup_inspection_endpoints(self) -> None:
        approved = self.client.post(
            "/api/system/mqtt/registrations/approve",
            headers={"X-Admin-Token": "test-token"},
            json={
                "addon_id": "vision",
                "access_mode": "both",
                "publish_topics": ["hexe/addons/vision/event/#"],
                "subscribe_topics": ["hexe/addons/vision/command/#"],
            },
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        grants = self.client.get("/api/system/mqtt/grants", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(grants.status_code, 200, grants.text)
        self.assertEqual(len(grants.json()["items"]), 1)

        one = self.client.get("/api/system/mqtt/grants/vision", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(one.status_code, 200, one.text)
        self.assertEqual(one.json()["grant"]["addon_id"], "vision")

        summary = self.client.get("/api/system/mqtt/setup-summary", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertIn("setup", summary.json())
        self.assertIn("broker", summary.json())
        self.assertIn("health", summary.json())
        self.assertIn("effective_status", summary.json())
        self.assertIn("last_authority_errors", summary.json())
        self.assertIn("last_provisioning_errors", summary.json())
        self.assertIn("reconciliation", summary.json())
        self.assertIn("bootstrap_publish", summary.json())
        self.assertIn("setup_error", summary.json()["setup"])
        self.assertIn("status", summary.json()["effective_status"])

    def test_setup_state_gates_provisioning_until_ready(self) -> None:
        approved = self.client.post(
            "/api/system/mqtt/registrations/approve",
            headers={"X-Admin-Token": "test-token"},
            json={
                "addon_id": "vision",
                "access_mode": "gateway",
                "publish_topics": ["hexe/addons/vision/state/#"],
                "subscribe_topics": [],
            },
        )
        self.assertEqual(approved.status_code, 200, approved.text)

        blocked = self.client.post(
            "/api/system/mqtt/registrations/vision/provision",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(blocked.status_code, 200, blocked.text)
        self.assertFalse(blocked.json()["ok"])
        self.assertEqual(blocked.json()["error"], "mqtt_setup_not_ready")

        setup_ready = self.client.post(
            "/api/system/mqtt/setup-state",
            headers={"X-Admin-Token": "test-token"},
            json={
                "requires_setup": True,
                "setup_complete": True,
                "setup_status": "ready",
                "broker_mode": "external",
                "direct_mqtt_supported": False,
                "authority_ready": True,
                "setup_error": None,
            },
        )
        self.assertEqual(setup_ready.status_code, 200, setup_ready.text)

        provision = self.client.post(
            "/api/system/mqtt/registrations/vision/provision",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(provision.status_code, 200, provision.text)
        self.assertTrue(provision.json()["ok"])

        summary = self.client.get("/api/system/mqtt/setup-summary", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertIsInstance(summary.json().get("last_provisioning_errors"), list)

    def test_reload_alias_and_health_endpoint(self) -> None:
        reload_resp = self.client.post("/api/system/mqtt/reload")
        self.assertEqual(reload_resp.status_code, 200, reload_resp.text)
        self.assertTrue(reload_resp.json().get("ok"))

        health_resp = self.client.get("/api/system/mqtt/health", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(health_resp.status_code, 200, health_resp.text)
        self.assertIn("effective_status", health_resp.json())

    def test_provision_scope_checks_for_service_token(self) -> None:
        no_scope = self.client.post(
            "/api/system/mqtt/registrations/vision/provision",
            headers={"Authorization": f"Bearer {self._token(sub='vision', scopes=['mqtt.register'])}"},
        )
        self.assertEqual(no_scope.status_code, 401, no_scope.text)
        self.assertEqual(no_scope.json()["detail"], "claim_scope_missing")


if __name__ == "__main__":
    unittest.main()
