from __future__ import annotations

import os
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.supervisor import SupervisorDomainService, build_supervisor_router
from app.system.auth.tokens import sign_hs256


class _Completed:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class _ProvisioningBackend:
    def __init__(self) -> None:
        self.calls = []

    def provision_wifi(self, *, body, adapter, validation):
        self.calls.append((body, adapter, validation))
        return {"ok": True, "status": "completed", "ack": True, "message": "provisioned"}


class _FailingProvisioningBackend:
    def provision_wifi(self, *, body, adapter, validation):
        raise RuntimeError("write_timeout")


class TestSupervisorBluetoothBroker(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(
            os.environ,
            {
                "HEXE_SUPERVISOR_ID": "sup-1",
                "HEXE_HARDWARE_LEASE_SECRET": "test-hardware-secret",
                "HEXE_HARDWARE_LEASE_VALIDATE_URL": "",
                "HEXE_SUPERVISOR_CORE_URL": "",
            },
            clear=False,
        )
        self.env_patch.start()
        self.service = SupervisorDomainService()
        self.service._bluetooth_summary = lambda: {  # type: ignore[method-assign]
            "bluetooth_present": True,
            "bluetooth_powered": True,
            "bluetooth_ensure_powered": True,
            "bluetooth_power_error": None,
            "bluetooth_adapters": [{"adapter": "hci0", "present": True, "powered": True}],
        }
        app = FastAPI()
        app.include_router(build_supervisor_router(self.service), prefix="/api")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()

    def _provisioning_context(self, *, onboarding_session_id: str = "onboard-1") -> dict:
        return {
            "contract_version": "1.0",
            "onboarding_session_id": onboarding_session_id,
            "target_node_id": "voice-node-1",
            "node_profile_id": "voice",
            "payload_schema_id": "hexe.voice_node.wifi_backend.v1",
            "pairing_nonce": "nonce-123456",
        }

    def _voice_payload(self) -> dict:
        return {
            "wifi_ssid": "OfficeNet",
            "wifi_password": "correct-password",
            "backend_host": "core.local",
            "http_port": 9001,
            "ws_port": 9001,
            "use_tls": False,
            "endpoint_name": "kitchen",
            "display_name": "Kitchen Voice",
        }

    def _provisioning_request(self, *, onboarding_session_id: str = "onboard-1") -> dict:
        return {
            "node_id": "node-1",
            "lease_token": self._lease_token(operation="ble.provision_wifi", provisioning=self._provisioning_context()),
            "adapter": "hci0",
            "target_address": "AA:BB:CC:DD:EE:FF",
            "credential_payload": self._voice_payload(),
            **self._provisioning_context(onboarding_session_id=onboarding_session_id),
        }

    def _lease_token(self, *, operation: str = "ble.scan", adapter: str | None = "hci0", provisioning: dict | None = None) -> str:
        now = int(time.time())
        claims = {
            "sub": "node-1",
            "aud": "hexe.hardware.bluetooth",
            "scp": [f"hardware.bluetooth.{operation}"],
            "iat": now,
            "exp": now + 600,
            "jti": "lease-1",
            "lease_id": "lease-1",
            "node_id": "node-1",
            "resource_type": "bluetooth",
            "operation": operation,
            "supervisor_id": "sup-1",
            "adapter": adapter,
        }
        if provisioning is not None:
            claims["provisioning"] = dict(provisioning)
        return sign_hs256({"alg": "HS256", "typ": "JWT", "kid": "hardware-v1"}, claims, secret="test-hardware-secret")

    def test_ble_scan_requires_matching_lease_scope(self) -> None:
        response = self.client.post(
            "/api/supervisor/hardware/bluetooth/ble/scan",
            json={"node_id": "node-1", "lease_token": self._lease_token(operation="ble.status"), "adapter": "hci0"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["error"], "claim_scope_missing")

    def test_ble_scan_uses_brokered_bluetoothctl_surface(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:3] == ["bluetoothctl", "--timeout", "2"]:
                return _Completed(stdout="[NEW] Device AA:BB:CC:DD:EE:FF Heart Sensor\n")
            if cmd == ["bluetoothctl", "devices"]:
                return _Completed(stdout="Device 11:22:33:44:55:66 Thermometer\n")
            return _Completed()

        with patch("app.supervisor.service.shutil.which", return_value="/usr/bin/bluetoothctl"):
            with patch("app.supervisor.service.subprocess.run", side_effect=fake_run):
                response = self.client.post(
                    "/api/supervisor/hardware/bluetooth/ble/scan",
                    json={
                        "node_id": "node-1",
                        "lease_token": self._lease_token(),
                        "adapter": "hci0",
                        "scan_seconds": 2,
                    },
                )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"], "ble.scan")
        self.assertEqual(payload["adapter"]["adapter"], "hci0")
        self.assertEqual(payload["revocation_check"], "local_token_only")
        self.assertEqual({item["address"] for item in payload["devices"]}, {"AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"})
        self.assertEqual(calls[0], ["bluetoothctl", "--timeout", "2", "scan", "on"])
        self.assertEqual(calls[1], ["bluetoothctl", "devices"])

    def test_ble_provision_wifi_requires_matching_lease_scope(self) -> None:
        request = self._provisioning_request()
        request["lease_token"] = self._lease_token(operation="ble.scan")

        response = self.client.post("/api/supervisor/hardware/bluetooth/ble/provision-wifi", json=request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["error"], "claim_scope_missing")

    def test_ble_provision_wifi_rejects_wrong_session_binding(self) -> None:
        request = self._provisioning_request(onboarding_session_id="onboard-2")

        response = self.client.post("/api/supervisor/hardware/bluetooth/ble/provision-wifi", json=request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["error"], "hardware_access_provisioning_onboarding_session_id_mismatch")

    def test_ble_provision_wifi_fails_closed_without_backend(self) -> None:
        response = self.client.post("/api/supervisor/hardware/bluetooth/ble/provision-wifi", json=self._provisioning_request())

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["operation"], "ble.provision_wifi")
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"], "gatt_backend_unavailable")
        self.assertEqual(payload["credential_payload"]["wifi_password"], "[REDACTED]")
        self.assertEqual(self.service._ble_provisioning_events[-1]["event"], "provision_wifi_rejected")

    def test_ble_provision_wifi_rejects_invalid_voice_payload(self) -> None:
        request = self._provisioning_request()
        request["credential_payload"]["wifi_password"] = "short"

        response = self.client.post("/api/supervisor/hardware/bluetooth/ble/provision-wifi", json=request)

        self.assertEqual(response.status_code, 422)

    def test_ble_provision_wifi_reports_backend_failure_without_secret_leak(self) -> None:
        self.service._ble_provisioning_backend = _FailingProvisioningBackend()

        response = self.client.post("/api/supervisor/hardware/bluetooth/ble/provision-wifi", json=self._provisioning_request())

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"], "gatt_backend_failed")
        self.assertEqual(payload["message"], "write_timeout")
        self.assertEqual(payload["credential_payload"]["wifi_password"], "[REDACTED]")

    def test_ble_provision_wifi_uses_gatt_backend_and_redacts_response(self) -> None:
        backend = _ProvisioningBackend()
        self.service._ble_provisioning_backend = backend

        response = self.client.post("/api/supervisor/hardware/bluetooth/ble/provision-wifi", json=self._provisioning_request())

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["credential_payload"]["wifi_password"], "[REDACTED]")
        self.assertEqual(payload["provisioning"]["target_node_id"], "voice-node-1")
        self.assertEqual(backend.calls[0][0].credential_payload.wifi_password, "correct-password")
        self.assertEqual(backend.calls[0][1]["adapter"], "hci0")
        self.assertEqual(self.service._ble_provisioning_events[-1]["event"], "provision_wifi_completed")


if __name__ == "__main__":
    unittest.main()
