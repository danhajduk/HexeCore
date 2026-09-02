from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.system import build_system_router
from app.system.audit import AuditLogStore
from app.system.onboarding import NodeRegistrationsStore, NodeTrustIssuanceService, NodeTrustStore
from app.system.onboarding.registrations import NodeRegistrationRecord
from app.system.onboarding.trust import NodeTrustRecord
from app.system.supervisors import SupervisorFleetStore, SupervisorHeartbeatRequest


class _FakeRegistry:
    def has_addon(self, addon_id: str) -> bool:
        return False

    def is_platform_managed(self, addon_id: str) -> bool:
        return False

    def set_enabled(self, addon_id: str, enabled: bool) -> None:
        return None

    def is_enabled(self, addon_id: str) -> bool:
        return False

    @property
    def errors(self):
        return []


class TestNodeHardwareAccessApi(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self.registrations = NodeRegistrationsStore(path=base / "node_registrations.json")
        self.trust_store = NodeTrustStore(path=base / "node_trust_records.json")
        self.trust_issuance = NodeTrustIssuanceService(self.trust_store)
        self.supervisors = SupervisorFleetStore(path=base / "supervisors.json")
        self.audit_store = AuditLogStore(str(base / "audit.log"))
        self.env_patch = patch.dict(
            os.environ,
            {
                "HEXE_ADMIN_TOKEN": "admin-token",
                "HEXE_HARDWARE_ACCESS_DB": str(base / "hardware_access.json"),
                "HEXE_HARDWARE_LEASE_SECRET": "test-hardware-secret",
            },
            clear=False,
        )
        self.env_patch.start()
        self._trusted_node("node-1", "node-token")
        self._supervisor(policy="allowed")

        app = FastAPI()
        app.include_router(
            build_system_router(
                _FakeRegistry(),
                node_registrations_store=self.registrations,
                node_trust_issuance=self.trust_issuance,
                supervisor_fleet_store=self.supervisors,
                audit_store=self.audit_store,
            ),
            prefix="/api",
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.tmpdir.cleanup()

    def _trusted_node(self, node_id: str, token: str) -> None:
        now = "2026-08-30T00:00:00+00:00"
        self.registrations.upsert(
            NodeRegistrationRecord(
                node_id=node_id,
                node_type="sensor-node",
                node_name="Sensor Node",
                node_software_version="1.0.0",
                requested_node_type="sensor-node",
                capabilities_summary=[],
                trust_status="trusted",
                source_onboarding_session_id="session-1",
                approved_by_user_id="admin",
                approved_at=now,
                created_at=now,
                updated_at=now,
                requested_task_families=["hardware.bluetooth"],
            )
        )
        self.trust_store.upsert(
            NodeTrustRecord(
                node_id=node_id,
                node_type="sensor-node",
                paired_core_id="hexe-core",
                node_trust_token=token,
                initial_baseline_policy={"version": "1", "rules": []},
                baseline_policy_version="1",
                activation_profile={"node_type": "sensor-node"},
                operational_mqtt_identity=f"hn_{node_id}",
                operational_mqtt_token="mqtt-token",
                operational_mqtt_host="127.0.0.1",
                operational_mqtt_port=1883,
                issued_at=now,
                source_session_id="session-1",
            )
        )

    def _supervisor(self, *, policy: str) -> None:
        self.supervisors.heartbeat(
            SupervisorHeartbeatRequest(
                supervisor_id="sup-1",
                supervisor_name="Supervisor 1",
                host_id="host-1",
                hostname="host-1",
                api_base_url="http://127.0.0.1:57665",
                transport="http",
                health_status="ok",
                lifecycle_state="running",
                resources={
                    "bluetooth_present": True,
                    "bluetooth_powered": True,
                    "bluetooth_adapters": [{"adapter": "hci0", "present": True, "powered": True}],
                },
                capabilities=["host_resources", "bluetooth", "bluetooth_governance"],
                metadata={"bluetooth": {"present": True, "powered": True, "policy": policy, "governed_by_core": True}},
            )
        )

    def test_exposes_hardware_access_request_schema(self) -> None:
        response = self.client.get("/api/system/nodes/hardware/access-requests/schema")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema_version"], "1")
        self.assertEqual(payload["resource_types"], ["bluetooth"])
        self.assertEqual(payload["operations"], ["ble.provision_wifi", "ble.scan", "ble.status"])
        self.assertIn("voice", payload["provisioning_payload_schemas"])

        schema = payload["request_schema"]
        self.assertEqual(schema["additionalProperties"], False)
        self.assertIn("node_id", schema["required"])
        properties = schema["properties"]
        self.assertEqual(properties["node_id"]["minLength"], 1)
        self.assertEqual(properties["resource_type"]["default"], "bluetooth")
        self.assertEqual(properties["operation"]["default"], "ble.scan")
        self.assertIn("ble.provision_wifi", properties["operation"]["enum"])
        self.assertIn("ble.scan", properties["operation"]["enum"])
        self.assertIn("ble.status", properties["operation"]["enum"])

    def test_exposes_voice_provisioning_payload_schema(self) -> None:
        response = self.client.get("/api/system/nodes/hardware/ble/provisioning/schemas/voice")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"], "ble.provision_wifi")
        self.assertEqual(payload["node_profile_id"], "voice")
        schema = payload["payload_schema"]["json_schema"]
        self.assertIn("wifi_ssid", schema["required"])
        self.assertIn("backend_host", schema["required"])
        self.assertEqual(schema["properties"]["http_port"]["minimum"], 1)
        self.assertEqual(schema["properties"]["http_port"]["maximum"], 65535)

    def test_provision_wifi_grants_scoped_lease_and_validates_session(self) -> None:
        provisioning = {
            "contract_version": "1.0",
            "schema_version": "1.0",
            "onboarding_session_id": "onboard-1",
            "target_node_id": "voice-node-1",
            "node_profile_id": "voice",
            "payload_schema_id": "hexe.voice_node.wifi_backend.v1",
            "endpoint_ephemeral_public_key": "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE",
            "pairing_nonce": "nonce-123456",
            "claim_code_ref": "claim-ref-1",
            "sequence": 1,
            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() + 600)),
        }
        created = self.client.post(
            "/api/system/nodes/hardware/access-requests",
            headers={"X-Node-Trust-Token": "node-token"},
            json={
                "node_id": "node-1",
                "resource_type": "bluetooth",
                "operation": "ble.provision_wifi",
                "adapter": "hci0",
                "provisioning": provisioning,
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        access = created.json()["access_request"]
        self.assertEqual(access["status"], "granted")
        self.assertEqual(access["operation"], "ble.provision_wifi")
        self.assertEqual(access["provisioning"]["target_node_id"], "voice-node-1")
        self.assertTrue(access["lease_token"])

        validated = self.client.post(
            "/api/system/hardware/leases/validate",
            headers={"X-Admin-Token": "admin-token"},
            json={
                "node_id": "node-1",
                "lease_token": access["lease_token"],
                "resource_type": "bluetooth",
                "operation": "ble.provision_wifi",
                "supervisor_id": "sup-1",
                "adapter": "hci0",
                "provisioning": provisioning,
            },
        )
        self.assertEqual(validated.status_code, 200, validated.text)
        self.assertTrue(validated.json()["valid"])

        wrong_session = dict(provisioning)
        wrong_session["onboarding_session_id"] = "onboard-2"
        invalid = self.client.post(
            "/api/system/hardware/leases/validate",
            headers={"X-Admin-Token": "admin-token"},
            json={
                "node_id": "node-1",
                "lease_token": access["lease_token"],
                "resource_type": "bluetooth",
                "operation": "ble.provision_wifi",
                "supervisor_id": "sup-1",
                "adapter": "hci0",
                "provisioning": wrong_session,
            },
        )
        self.assertEqual(invalid.status_code, 200, invalid.text)
        self.assertFalse(invalid.json()["valid"])
        self.assertEqual(invalid.json()["error"], "hardware_access_provisioning_onboarding_session_id_mismatch")

        wrong_claim_code = dict(provisioning)
        wrong_claim_code["claim_code_ref"] = "claim-ref-2"
        invalid_claim = self.client.post(
            "/api/system/hardware/leases/validate",
            headers={"X-Admin-Token": "admin-token"},
            json={
                "node_id": "node-1",
                "lease_token": access["lease_token"],
                "resource_type": "bluetooth",
                "operation": "ble.provision_wifi",
                "supervisor_id": "sup-1",
                "adapter": "hci0",
                "provisioning": wrong_claim_code,
            },
        )
        self.assertEqual(invalid_claim.status_code, 200, invalid_claim.text)
        self.assertFalse(invalid_claim.json()["valid"])
        self.assertEqual(invalid_claim.json()["error"], "hardware_access_provisioning_claim_code_ref_mismatch")

    def test_allowed_policy_grants_and_release_invalidates_lease(self) -> None:
        created = self.client.post(
            "/api/system/nodes/hardware/access-requests",
            headers={"X-Node-Trust-Token": "node-token"},
            json={"node_id": "node-1", "resource_type": "bluetooth", "operation": "ble.scan", "adapter": "hci0"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        access = created.json()["access_request"]
        self.assertEqual(access["status"], "granted")
        self.assertTrue(access["lease_token"])

        validated = self.client.post(
            "/api/system/hardware/leases/validate",
            headers={"X-Admin-Token": "admin-token"},
            json={
                "node_id": "node-1",
                "lease_token": access["lease_token"],
                "resource_type": "bluetooth",
                "operation": "ble.scan",
                "supervisor_id": "sup-1",
                "adapter": "hci0",
            },
        )
        self.assertEqual(validated.status_code, 200, validated.text)
        self.assertTrue(validated.json()["valid"])

        released = self.client.post(
            f"/api/system/nodes/hardware/leases/{access['lease_id']}/release",
            headers={"X-Node-Trust-Token": "node-token"},
            json={"node_id": "node-1"},
        )
        self.assertEqual(released.status_code, 200, released.text)
        self.assertEqual(released.json()["access_request"]["status"], "released")

        invalid = self.client.post(
            "/api/system/hardware/leases/validate",
            headers={"X-Admin-Token": "admin-token"},
            json={
                "node_id": "node-1",
                "lease_token": access["lease_token"],
                "resource_type": "bluetooth",
                "operation": "ble.scan",
                "supervisor_id": "sup-1",
                "adapter": "hci0",
            },
        )
        self.assertEqual(invalid.status_code, 200, invalid.text)
        self.assertFalse(invalid.json()["valid"])
        self.assertEqual(invalid.json()["error"], "hardware_access_lease_released")

    def test_disabled_policy_denies_request(self) -> None:
        self._supervisor(policy="disabled")
        created = self.client.post(
            "/api/system/nodes/hardware/access-requests",
            headers={"X-Node-Trust-Token": "node-token"},
            json={"node_id": "node-1", "resource_type": "bluetooth", "operation": "ble.scan"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        access = created.json()["access_request"]
        self.assertEqual(access["status"], "denied")
        self.assertEqual(access["decision_reason"], "bluetooth_policy_disabled")
        self.assertNotIn("lease_token", access)

    def test_ask_policy_returns_pending_and_admin_can_approve(self) -> None:
        self._supervisor(policy="ask")
        created = self.client.post(
            "/api/system/nodes/hardware/access-requests",
            headers={"X-Node-Trust-Token": "node-token"},
            json={"node_id": "node-1", "resource_type": "bluetooth", "operation": "ble.status"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        access = created.json()["access_request"]
        self.assertEqual(access["status"], "pending")

        decided = self.client.post(
            f"/api/system/hardware/access-requests/{access['request_id']}/decision",
            headers={"X-Admin-Token": "admin-token"},
            json={"decision": "approve", "duration_s": 60},
        )
        self.assertEqual(decided.status_code, 200, decided.text)
        approved = decided.json()["access_request"]
        self.assertEqual(approved["status"], "granted")
        self.assertTrue(approved["lease_token"])


if __name__ == "__main__":
    unittest.main()
