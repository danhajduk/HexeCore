from __future__ import annotations

import os
import socket
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
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
                "HEXE_BLE_PAIRING_SESSIONS_DB": str(base / "ble_pairing_sessions.json"),
                "HEXE_HARDWARE_LEASE_SECRET": "test-hardware-secret",
            },
            clear=False,
        )
        self.env_patch.start()
        self._trusted_node("node-1", "node-token")
        self._supervisor(policy="allowed")

        app = FastAPI()
        self.app = app
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

    def _supervisor(
        self,
        *,
        policy: str,
        supervisor_id: str = "sup-1",
        supervisor_name: str = "Supervisor 1",
        host_id: str = "host-1",
        transport: str = "http",
        api_base_url: str | None = "http://127.0.0.1:57665",
        capabilities: list[str] | None = None,
        metadata: dict | None = None,
    ) -> None:
        bluetooth_metadata = {"present": True, "powered": True, "policy": policy, "governed_by_core": True}
        if metadata:
            bluetooth_metadata.update(metadata)
        self.supervisors.heartbeat(
            SupervisorHeartbeatRequest(
                supervisor_id=supervisor_id,
                supervisor_name=supervisor_name,
                host_id=host_id,
                hostname=host_id,
                api_base_url=api_base_url,
                transport=transport,
                health_status="ok",
                lifecycle_state="running",
                resources={
                    "bluetooth_present": True,
                    "bluetooth_powered": True,
                    "bluetooth_adapters": [{"adapter": "hci0", "present": True, "powered": True}],
                },
                capabilities=capabilities or ["host_resources", "bluetooth", "bluetooth_governance"],
                metadata={"bluetooth": bluetooth_metadata},
            )
        )

    def test_exposes_hardware_access_request_schema(self) -> None:
        response = self.client.get("/api/system/nodes/hardware/access-requests/schema")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema_version"], "1")
        self.assertEqual(payload["resource_types"], ["bluetooth"])
        self.assertEqual(payload["operations"], ["ble.host_pairing_advert", "ble.provision_wifi", "ble.read_identity", "ble.scan", "ble.status"])
        self.assertIn("voice", payload["provisioning_payload_schemas"])
        pairing_schema = payload["core_published_pairing_session_schema"]
        self.assertEqual(pairing_schema["service_uuid"], "7f9c0000-5f04-4d8b-9a46-7c0f7a100000")
        self.assertEqual(pairing_schema["advertisement_schema"]["properties"]["session_role"]["const"], "host_pairing_advert")
        self.assertIn("device_id", pairing_schema["endpoint_identity_schema"]["required"])
        self.assertEqual(pairing_schema["wifi_handoff_required_fields"], ["onboarding_session_id", "device_id"])

        schema = payload["request_schema"]
        self.assertEqual(schema["additionalProperties"], False)
        self.assertIn("node_id", schema["required"])
        properties = schema["properties"]
        self.assertEqual(properties["node_id"]["minLength"], 1)
        self.assertEqual(properties["resource_type"]["default"], "bluetooth")
        self.assertEqual(properties["operation"]["default"], "ble.scan")
        self.assertIn("ble.provision_wifi", properties["operation"]["enum"])
        self.assertIn("ble.host_pairing_advert", properties["operation"]["enum"])
        self.assertIn("ble.read_identity", properties["operation"]["enum"])
        self.assertIn("ble.scan", properties["operation"]["enum"])
        self.assertIn("ble.status", properties["operation"]["enum"])

    def test_exposes_voice_provisioning_payload_schema(self) -> None:
        response = self.client.get("/api/system/nodes/hardware/ble/provisioning/schemas/voice")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"], "ble.provision_wifi")
        self.assertEqual(payload["node_profile_id"], "voice")
        pairing_schema = payload["core_published_pairing_session_schema"]
        self.assertIn("device_id", pairing_schema["endpoint_identity_schema"]["required"])
        self.assertEqual(pairing_schema["pairing_offer_schema"]["properties"]["payload_schema_id"]["const"], "hexe.voice_node.wifi_backend.v1")
        schema = payload["payload_schema"]["json_schema"]
        self.assertIn("wifi_ssid", schema["required"])
        self.assertIn("backend_host", schema["required"])
        self.assertEqual(schema["properties"]["http_port"]["minimum"], 1)
        self.assertEqual(schema["properties"]["http_port"]["maximum"], 65535)

    def test_ble_scan_fans_out_to_bluetooth_supervisors_and_releases_leases(self) -> None:
        self._supervisor(
            policy="allowed",
            supervisor_id="sup-2",
            supervisor_name="Supervisor 2",
            host_id="host-2",
            api_base_url="http://127.0.0.1:57666",
        )
        calls: list[dict] = []

        def fake_post(url: str, *, json: dict, timeout: float):
            calls.append({"url": url, "json": dict(json), "timeout": timeout})
            payload = {
                "ok": True,
                "status": "completed",
                "operation": "ble.scan",
                "adapter": json.get("adapter"),
                "service_uuid": json.get("service_uuid"),
                "scan_seconds": json.get("scan_seconds"),
                "devices": [],
                "matching_devices": [],
            }
            if "57666" in url:
                payload["devices"] = [
                    {
                        "address": "AA:BB:CC:DD:EE:FF",
                        "name": "Hexe Voice PE",
                        "transport": "ble",
                        "service_uuid_match": True,
                        "matched_service_uuid": "7f9c0000-5f04-4d8b-9a46-7c0f7a100000",
                    }
                ]
                payload["matching_devices"] = list(payload["devices"])
            return httpx.Response(200, json=payload)

        with patch("app.api.system_legacy.httpx.post", side_effect=fake_post):
            response = self.client.post(
                "/api/system/nodes/hardware/bluetooth/ble/scan",
                headers={"X-Node-Trust-Token": "node-token"},
                json={
                    "node_id": "node-1",
                    "adapter": "hci0",
                    "service_uuid": "7f9c0000-5f04-4d8b-9a46-7c0f7a100000",
                    "scan_seconds": 60,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["mode"], "fleet")
        self.assertEqual(payload["supervisor_count"], 2)
        self.assertEqual(payload["completed_supervisor_count"], 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual({call["json"]["scan_seconds"] for call in calls}, {60})
        self.assertEqual({call["timeout"] for call in calls}, {70.0})
        self.assertTrue(all(call["json"].get("lease_token") for call in calls))
        self.assertEqual(payload["devices"][0]["address"], "AA:BB:CC:DD:EE:FF")
        self.assertEqual(payload["devices"][0]["supervisor_id"], "sup-2")

        access_list = self.client.get(
            "/api/system/nodes/node-1/hardware/access-requests",
            headers={"X-Node-Trust-Token": "node-token"},
        )
        self.assertEqual(access_list.status_code, 200, access_list.text)
        self.assertEqual({item["status"] for item in access_list.json()["items"]}, {"released"})

    def test_ble_scan_uses_local_client_for_same_host_socket_supervisor(self) -> None:
        self._supervisor(
            policy="allowed",
            supervisor_id="hxe-supervisor",
            supervisor_name="Local Socket Supervisor",
            host_id=socket.gethostname(),
            transport="socket",
            api_base_url=None,
            metadata={"local_core_runtime_report": True},
        )

        class _LocalSupervisorClient:
            def __init__(self) -> None:
                self.requests: list[dict] = []

            def request_json(self, method: str, path: str, *, payload: dict | None = None, params: dict | None = None, timeout_s: float | None = None):
                self.requests.append({"method": method, "path": path, "payload": dict(payload or {}), "timeout_s": timeout_s})
                return {
                    "ok": True,
                    "status": "completed",
                    "operation": "ble.scan",
                    "adapter": payload.get("adapter"),
                    "service_uuid": payload.get("service_uuid"),
                    "scan_seconds": payload.get("scan_seconds"),
                    "devices": [
                        {
                            "address": "AA:BB:CC:DD:EE:FF",
                            "name": "Hexe Voice PE",
                            "transport": "ble",
                            "service_uuid_match": True,
                        }
                    ],
                    "matching_devices": [
                        {
                            "address": "AA:BB:CC:DD:EE:FF",
                            "name": "Hexe Voice PE",
                            "transport": "ble",
                            "service_uuid_match": True,
                        }
                    ],
                }

        local_client = _LocalSupervisorClient()
        self.app.state.supervisor_client = local_client
        response = self.client.post(
            "/api/system/nodes/hardware/bluetooth/ble/scan",
            headers={"X-Node-Trust-Token": "node-token"},
            json={
                "node_id": "node-1",
                "supervisor_id": "hxe-supervisor",
                "adapter": "hci0",
                "service_uuid": "7f9c0000-5f04-4d8b-9a46-7c0f7a100000",
                "scan_seconds": 60,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["completed_supervisor_count"], 1)
        self.assertEqual(payload["devices"][0]["supervisor_id"], "hxe-supervisor")
        self.assertEqual(local_client.requests[0]["path"], "/api/supervisor/hardware/bluetooth/ble/scan")
        self.assertEqual(local_client.requests[0]["timeout_s"], 70.0)

    def test_ble_pairing_session_lifecycle_uses_bluetooth_supervisor(self) -> None:
        calls: list[dict] = []

        def endpoint_identity(session_id: str) -> dict:
            return {
                "contract_version": "1.0",
                "onboarding_session_id": session_id,
                "device_id": "hexe-pe-a0-85-e3-f0-e1-6e",
                "node_hardware_id": "A0:85:E3:F0:E1:6E",
                "target_node_id": "voice-node-a0",
                "board_profile": "ha_voice_pe",
                "firmware_version": "min-fw-test",
                "application_type": "hexe_voice",
                "provisioning_mode": "core_published_pairing",
                "endpoint_ephemeral_public_key": "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE",
                "supported_payload_schemas": ["hexe.voice_node.wifi_backend.v1"],
                "provisioning_state": "awaiting_credentials",
            }

        def fake_post(url: str, *, json: dict, timeout: float):
            calls.append({"url": url, "json": dict(json), "timeout": timeout})
            session_id = str(json.get("onboarding_session_id"))
            if url.endswith("/pairing-advert/start"):
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "status": "advertising",
                        "operation": "ble.host_pairing_advert",
                        "supervisor_id": "sup-1",
                        "adapter": {"adapter": json.get("adapter") or "hci0", "present": True, "powered": True},
                        "onboarding_session_id": session_id,
                        "session_hint": json.get("session_hint"),
                        "advertising": True,
                    },
                )
            if url.endswith("/pairing-advert/status"):
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "status": "endpoint_identity_received",
                        "operation": "ble.host_pairing_advert",
                        "supervisor_id": "sup-1",
                        "adapter": {"adapter": json.get("adapter") or "hci0", "present": True, "powered": True},
                        "onboarding_session_id": session_id,
                        "endpoint_identity": endpoint_identity(session_id),
                        "advertising": True,
                    },
                )
            if url.endswith("/pairing-advert/stop"):
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "status": "stopped",
                        "operation": "ble.host_pairing_advert",
                        "supervisor_id": "sup-1",
                        "adapter": {"adapter": json.get("adapter") or "hci0", "present": True, "powered": True},
                        "onboarding_session_id": session_id,
                        "advertising": False,
                    },
                )
            raise AssertionError(f"unexpected url: {url}")

        with patch("app.api.system_legacy.httpx.post", side_effect=fake_post):
            created = self.client.post(
                "/api/system/hardware/bluetooth/ble/pairing-sessions",
                headers={"X-Admin-Token": "admin-token"},
                json={"adapter": "hci0", "duration_s": 300, "reason": "test add device"},
            )

            self.assertEqual(created.status_code, 200, created.text)
            session = created.json()["pairing_session"]
            session_id = session["session_id"]
            self.assertTrue(session_id.startswith("blepair_"))
            self.assertEqual(session["status"], "waiting")
            self.assertEqual(session["supervisor_results"][0]["status"], "advertising")
            self.assertNotIn("session_token", session["supervisor_results"][0])
            self.assertEqual(calls[0]["url"], "http://127.0.0.1:57665/api/supervisor/hardware/bluetooth/ble/pairing-advert/start")
            self.assertTrue(calls[0]["json"]["session_token"])
            self.assertEqual(calls[0]["json"]["payload_schema_id"], "hexe.voice_node.wifi_backend.v1")

            found = self.client.get(
                f"/api/system/hardware/bluetooth/ble/pairing-sessions/{session_id}",
                headers={"X-Admin-Token": "admin-token"},
            )
            self.assertEqual(found.status_code, 200, found.text)
            found_session = found.json()["pairing_session"]
            self.assertEqual(found_session["status"], "found")
            self.assertEqual(found_session["endpoint_identity"]["device_id"], "hexe-pe-a0-85-e3-f0-e1-6e")
            self.assertEqual(found_session["endpoint_identity"]["board_profile"], "ha_voice_pe")
            self.assertEqual(calls[1]["json"]["adapter"], "hci0")

            approved = self.client.post(
                f"/api/system/hardware/bluetooth/ble/pairing-sessions/{session_id}/approve",
                headers={"X-Admin-Token": "admin-token"},
                json={"device_id": "hexe-pe-a0-85-e3-f0-e1-6e"},
            )
            self.assertEqual(approved.status_code, 200, approved.text)
            approved_session = approved.json()["pairing_session"]
            self.assertEqual(approved_session["status"], "approved")
            self.assertEqual(approved_session["approved_device_id"], "hexe-pe-a0-85-e3-f0-e1-6e")

            canceled_created = self.client.post(
                "/api/system/hardware/bluetooth/ble/pairing-sessions",
                headers={"X-Admin-Token": "admin-token"},
                json={"adapter": "hci0", "duration_s": 300, "reason": "test cancel"},
            )
            cancel_session_id = canceled_created.json()["pairing_session"]["session_id"]
            canceled = self.client.post(
                f"/api/system/hardware/bluetooth/ble/pairing-sessions/{cancel_session_id}/cancel",
                headers={"X-Admin-Token": "admin-token"},
                json={"reason": "operator closed dialog"},
            )

        self.assertEqual(canceled.status_code, 200, canceled.text)
        canceled_session = canceled.json()["pairing_session"]
        self.assertEqual(canceled_session["status"], "canceled")
        self.assertTrue(any(call["url"].endswith("/pairing-advert/stop") for call in calls))
        self.assertTrue(all(not isinstance(call["json"].get("adapter"), dict) for call in calls))

    def test_node_ble_pairing_session_lifecycle_uses_trusted_node_governance(self) -> None:
        self._trusted_node("node-2", "node-2-token")
        calls: list[dict] = []

        def endpoint_identity(session_id: str) -> dict:
            return {
                "contract_version": "1.0",
                "onboarding_session_id": session_id,
                "device_id": "hexe-pe-a0-85-e3-f0-e1-6e",
                "node_hardware_id": "A0:85:E3:F0:E1:6E",
                "target_node_id": "voice-node-a0",
                "board_profile": "ha_voice_pe",
                "firmware_version": "min-fw-test",
                "application_type": "hexe_voice",
                "provisioning_mode": "core_published_pairing",
                "endpoint_ephemeral_public_key": "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE",
                "supported_payload_schemas": ["hexe.voice_node.wifi_backend.v1"],
                "provisioning_state": "awaiting_credentials",
            }

        def fake_post(url: str, *, json: dict, timeout: float):
            calls.append({"url": url, "json": dict(json), "timeout": timeout})
            session_id = str(json.get("onboarding_session_id"))
            if url.endswith("/pairing-advert/start"):
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "status": "advertising",
                        "operation": "ble.host_pairing_advert",
                        "supervisor_id": "sup-1",
                        "adapter": {"adapter": json.get("adapter") or "hci0", "present": True, "powered": True},
                        "onboarding_session_id": session_id,
                        "session_hint": json.get("session_hint"),
                        "advertising": True,
                    },
                )
            if url.endswith("/pairing-advert/status"):
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "status": "endpoint_identity_received",
                        "operation": "ble.host_pairing_advert",
                        "supervisor_id": "sup-1",
                        "adapter": {"adapter": json.get("adapter") or "hci0", "present": True, "powered": True},
                        "onboarding_session_id": session_id,
                        "endpoint_identity": endpoint_identity(session_id),
                        "advertising": True,
                    },
                )
            if url.endswith("/pairing-advert/stop"):
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "status": "stopped",
                        "operation": "ble.host_pairing_advert",
                        "supervisor_id": "sup-1",
                        "adapter": {"adapter": json.get("adapter") or "hci0", "present": True, "powered": True},
                        "onboarding_session_id": session_id,
                        "advertising": False,
                    },
                )
            raise AssertionError(f"unexpected url: {url}")

        with patch("app.api.system_legacy.httpx.post", side_effect=fake_post):
            created = self.client.post(
                "/api/system/nodes/hardware/bluetooth/ble/pairing-sessions",
                headers={"X-Node-Trust-Token": "node-token"},
                json={"node_id": "node-1", "adapter": "hci0", "duration_s": 300, "reason": "test add device"},
            )

            self.assertEqual(created.status_code, 200, created.text)
            session = created.json()["pairing_session"]
            session_id = session["session_id"]
            self.assertEqual(session["requesting_node_id"], "node-1")
            self.assertEqual(session["status"], "waiting")
            self.assertEqual(session["supervisor_results"][0]["status"], "advertising")
            self.assertNotIn("session_token", session["supervisor_results"][0])
            self.assertTrue(calls[0]["json"]["session_token"])

            blocked = self.client.get(
                f"/api/system/nodes/hardware/bluetooth/ble/pairing-sessions/{session_id}",
                headers={"X-Node-Trust-Token": "node-2-token"},
                params={"node_id": "node-2"},
            )
            self.assertEqual(blocked.status_code, 403, blocked.text)

            found = self.client.get(
                f"/api/system/nodes/hardware/bluetooth/ble/pairing-sessions/{session_id}",
                headers={"X-Node-Trust-Token": "node-token"},
                params={"node_id": "node-1"},
            )
            self.assertEqual(found.status_code, 200, found.text)
            found_session = found.json()["pairing_session"]
            self.assertEqual(found_session["status"], "found")
            self.assertEqual(found_session["endpoint_identity"]["device_id"], "hexe-pe-a0-85-e3-f0-e1-6e")

            approved = self.client.post(
                f"/api/system/nodes/hardware/bluetooth/ble/pairing-sessions/{session_id}/approve",
                headers={"X-Node-Trust-Token": "node-token"},
                json={"node_id": "node-1", "device_id": "hexe-pe-a0-85-e3-f0-e1-6e"},
            )
            self.assertEqual(approved.status_code, 200, approved.text)
            self.assertEqual(approved.json()["pairing_session"]["status"], "approved")

            canceled_created = self.client.post(
                "/api/system/nodes/hardware/bluetooth/ble/pairing-sessions",
                headers={"X-Node-Trust-Token": "node-token"},
                json={"node_id": "node-1", "adapter": "hci0", "duration_s": 300, "reason": "test cancel"},
            )
            cancel_session_id = canceled_created.json()["pairing_session"]["session_id"]
            canceled = self.client.post(
                f"/api/system/nodes/hardware/bluetooth/ble/pairing-sessions/{cancel_session_id}/cancel",
                headers={"X-Node-Trust-Token": "node-token"},
                json={"node_id": "node-1", "reason": "operator closed dialog"},
            )

        self.assertEqual(canceled.status_code, 200, canceled.text)
        self.assertEqual(canceled.json()["pairing_session"]["status"], "canceled")
        self.assertTrue(any(call["url"].endswith("/pairing-advert/stop") for call in calls))

    def test_node_ble_pairing_start_reuses_active_session(self) -> None:
        calls: list[dict] = []

        def endpoint_identity(session_id: str) -> dict:
            return {
                "contract_version": "1.0",
                "onboarding_session_id": session_id,
                "device_id": "hexe-pe-a0-85-e3-f0-e1-6e",
                "node_hardware_id": "A0:85:E3:F0:E1:6E",
                "target_node_id": "voice-node-a0",
                "board_profile": "ha_voice_pe",
                "firmware_version": "min-fw-test",
                "application_type": "hexe_voice",
                "provisioning_mode": "core_published_pairing",
                "endpoint_ephemeral_public_key": "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE",
                "supported_payload_schemas": ["hexe.voice_node.wifi_backend.v1"],
                "provisioning_state": "awaiting_credentials",
            }

        def fake_post(url: str, *, json: dict, timeout: float):
            calls.append({"url": url, "json": dict(json), "timeout": timeout})
            session_id = str(json.get("onboarding_session_id"))
            if url.endswith("/pairing-advert/start"):
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "status": "advertising",
                        "operation": "ble.host_pairing_advert",
                        "supervisor_id": "sup-1",
                        "adapter": {"adapter": json.get("adapter") or "hci0", "present": True, "powered": True},
                        "onboarding_session_id": session_id,
                        "session_hint": json.get("session_hint"),
                        "advertising": True,
                    },
                )
            if url.endswith("/pairing-advert/status"):
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "status": "endpoint_identity_received",
                        "operation": "ble.host_pairing_advert",
                        "supervisor_id": "sup-1",
                        "adapter": {"adapter": json.get("adapter") or "hci0", "present": True, "powered": True},
                        "onboarding_session_id": session_id,
                        "endpoint_identity": endpoint_identity(session_id),
                        "advertising": True,
                    },
                )
            raise AssertionError(f"unexpected url: {url}")

        with patch("app.api.system_legacy.httpx.post", side_effect=fake_post):
            created = self.client.post(
                "/api/system/nodes/hardware/bluetooth/ble/pairing-sessions",
                headers={"X-Node-Trust-Token": "node-token"},
                json={"node_id": "node-1", "adapter": "hci0", "duration_s": 300, "reason": "test add device"},
            )
            repeated = self.client.post(
                "/api/system/nodes/hardware/bluetooth/ble/pairing-sessions",
                headers={"X-Node-Trust-Token": "node-token"},
                json={"node_id": "node-1", "adapter": "hci0", "duration_s": 300, "reason": "test add device"},
            )

        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(repeated.status_code, 200, repeated.text)
        created_session = created.json()["pairing_session"]
        repeated_session = repeated.json()["pairing_session"]
        self.assertEqual(repeated_session["session_id"], created_session["session_id"])
        self.assertEqual(repeated_session["status"], "found")
        self.assertEqual(sum(1 for call in calls if call["url"].endswith("/pairing-advert/start")), 1)
        self.assertEqual(sum(1 for call in calls if call["url"].endswith("/pairing-advert/status")), 1)

    def test_ble_identity_uses_local_client_and_releases_lease(self) -> None:
        self._supervisor(
            policy="allowed",
            supervisor_id="hxe-supervisor",
            supervisor_name="Local Socket Supervisor",
            host_id=socket.gethostname(),
            transport="socket",
            api_base_url=None,
            metadata={"local_core_runtime_report": True},
        )

        class _LocalSupervisorClient:
            def __init__(self) -> None:
                self.requests: list[dict] = []

            def request_json(self, method: str, path: str, *, payload: dict | None = None, params: dict | None = None, timeout_s: float | None = None):
                self.requests.append({"method": method, "path": path, "payload": dict(payload or {}), "timeout_s": timeout_s})
                return {
                    "ok": True,
                    "status": "completed",
                    "operation": "ble.read_identity",
                    "target_address": payload.get("target_address"),
                    "onboarding": {
                        "target_node_id": "hexe-pe-1",
                        "onboarding_session_id": "recovery-ble-1234",
                        "pairing_nonce": "nonce-123456",
                        "board_profile": "ha_voice_pe",
                        "provisioning_mode": "local_recovery",
                    },
                }

        local_client = _LocalSupervisorClient()
        self.app.state.supervisor_client = local_client
        response = self.client.post(
            "/api/system/nodes/hardware/bluetooth/ble/identity",
            headers={"X-Node-Trust-Token": "node-token"},
            json={
                "node_id": "node-1",
                "supervisor_id": "hxe-supervisor",
                "adapter": "hci0",
                "target_address": "AA:BB:CC:DD:EE:FF",
                "timeout_s": 20,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"], "ble.read_identity")
        self.assertEqual(payload["completed_supervisor_count"], 1)
        self.assertEqual(payload["identity"]["board_profile"], "ha_voice_pe")
        self.assertEqual(payload["identity"]["onboarding_session_id"], "recovery-ble-1234")
        self.assertEqual(local_client.requests[0]["path"], "/api/supervisor/hardware/bluetooth/ble/identity")
        self.assertEqual(local_client.requests[0]["payload"]["target_address"], "AA:BB:CC:DD:EE:FF")
        self.assertEqual(local_client.requests[0]["payload"]["lease_token"] is not None, True)
        self.assertEqual(local_client.requests[0]["timeout_s"], 100.0)
        access_list = self.client.get(
            "/api/system/nodes/node-1/hardware/access-requests",
            headers={"X-Node-Trust-Token": "node-token"},
        )
        self.assertEqual({item["status"] for item in access_list.json()["items"]}, {"released"})

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

    def test_unspecified_supervisor_prefers_local_attached_bluetooth_broker(self) -> None:
        self._supervisor(
            policy="allowed",
            supervisor_id="remote-sup",
            supervisor_name="Remote Supervisor",
            host_id="remote-host",
            transport="socket",
            api_base_url=None,
        )
        self._supervisor(
            policy="allowed",
            supervisor_id="local-sup",
            supervisor_name="Local Supervisor",
            host_id="local-host",
            transport="local",
            api_base_url=None,
            capabilities=["host_resources", "bluetooth", "bluetooth_governance", "local_core_attached"],
        )

        created = self.client.post(
            "/api/system/nodes/hardware/access-requests",
            headers={"X-Node-Trust-Token": "node-token"},
            json={"node_id": "node-1", "resource_type": "bluetooth", "operation": "ble.scan", "adapter": "hci0"},
        )

        self.assertEqual(created.status_code, 200, created.text)
        access = created.json()["access_request"]
        self.assertEqual(access["status"], "granted")
        self.assertEqual(access["supervisor_id"], "local-sup")

    def test_unspecified_supervisor_prefers_same_host_broker_over_fresher_remote(self) -> None:
        with patch("app.system.hardware.socket.gethostname", return_value="local-host"):
            self._supervisor(
                policy="allowed",
                supervisor_id="same-host-sup",
                supervisor_name="Same Host Supervisor",
                host_id="local-host",
                transport="socket",
                api_base_url=None,
            )
            self._supervisor(
                policy="allowed",
                supervisor_id="remote-sup",
                supervisor_name="Remote Supervisor",
                host_id="remote-host",
                transport="socket",
                api_base_url=None,
            )

            created = self.client.post(
                "/api/system/nodes/hardware/access-requests",
                headers={"X-Node-Trust-Token": "node-token"},
                json={"node_id": "node-1", "resource_type": "bluetooth", "operation": "ble.scan", "adapter": "hci0"},
            )

        self.assertEqual(created.status_code, 200, created.text)
        access = created.json()["access_request"]
        self.assertEqual(access["status"], "granted")
        self.assertEqual(access["supervisor_id"], "same-host-sup")

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
