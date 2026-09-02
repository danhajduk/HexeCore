from __future__ import annotations

import os
import time
import base64
import json
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.supervisor import SupervisorDomainService, build_supervisor_router
from app.system.auth.tokens import sign_hs256
from app.system.hardware import BLE_PROVISIONING_CONTRACT_VERSION, BLE_PROVISIONING_KEY_AGREEMENT


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _future_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() + 600))


class _Completed:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class _ProvisioningBackend:
    def __init__(self) -> None:
        self.calls = []

    def provision_wifi(self, *, adapter, validation, envelope, target_address, timeout_s):
        self.calls.append((adapter, validation, envelope, target_address, timeout_s))
        return {"ok": True, "status": "completed", "ack": True, "message": "provisioned"}


class _FailingProvisioningBackend:
    def provision_wifi(self, *, adapter, validation, envelope, target_address, timeout_s):
        raise RuntimeError(f"write_timeout:{envelope['ciphertext']}:correct-password")


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
        self.endpoint_private_key = x25519.X25519PrivateKey.generate()
        self.endpoint_public_key = _b64url_encode(
            self.endpoint_private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        )
        self.provisioning_expires_at = _future_iso()
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
            "schema_version": "1.0",
            "onboarding_session_id": onboarding_session_id,
            "target_node_id": "voice-node-1",
            "node_profile_id": "voice",
            "payload_schema_id": "hexe.voice_node.wifi_backend.v1",
            "endpoint_ephemeral_public_key": self.endpoint_public_key,
            "pairing_nonce": "nonce-123456",
            "claim_code_ref": "claim-ref-1",
            "sequence": 1,
            "expires_at": self.provisioning_expires_at,
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

    def test_ble_provision_wifi_rejects_wrong_claim_code_binding(self) -> None:
        request = self._provisioning_request()
        request["claim_code_ref"] = "claim-ref-2"

        response = self.client.post("/api/supervisor/hardware/bluetooth/ble/provision-wifi", json=request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["error"], "hardware_access_provisioning_claim_code_ref_mismatch")

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
        self.assertEqual(payload["message"], "write_timeout:[REDACTED]:[REDACTED]")
        self.assertEqual(payload["credential_payload"]["wifi_password"], "[REDACTED]")
        self.assertEqual(payload["provisioning_envelope"]["ciphertext"], "[REDACTED]")

    def test_ble_provision_wifi_writes_encrypted_envelope_and_redacts_response(self) -> None:
        backend = _ProvisioningBackend()
        self.service._ble_provisioning_backend = backend

        response = self.client.post("/api/supervisor/hardware/bluetooth/ble/provision-wifi", json=self._provisioning_request())

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["credential_payload"]["wifi_password"], "[REDACTED]")
        self.assertEqual(payload["provisioning"]["target_node_id"], "voice-node-1")
        self.assertEqual(payload["provisioning_envelope"]["ciphertext"], "[REDACTED]")
        adapter, _validation, envelope, target_address, timeout_s = backend.calls[0]
        self.assertEqual(adapter["adapter"], "hci0")
        self.assertEqual(target_address, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(timeout_s, 30)
        self.assertEqual(envelope["schema_version"], "1.0")
        self.assertEqual(envelope["payload_schema_id"], "hexe.voice_node.wifi_backend.v1")
        self.assertEqual(envelope["contract_version"], "1.0")
        self.assertEqual(envelope["sequence"], 1)
        self.assertEqual(envelope["expires_at"], self.provisioning_expires_at)
        self.assertEqual(envelope["algorithm"], "aes-256-gcm")
        decrypted = self._decrypt_envelope(envelope)
        self.assertEqual(decrypted["credential_payload"]["wifi_password"], "correct-password")
        self.assertEqual(decrypted["credential_payload"]["backend_host"], "core.local")
        self.assertEqual(self.service._ble_provisioning_events[-1]["event"], "provision_wifi_completed")
        self.assertNotIn("correct-password", json.dumps(self.service._ble_provisioning_events))

    def _decrypt_envelope(self, envelope: dict) -> dict:
        supervisor_public_key = x25519.X25519PublicKey.from_public_bytes(_b64url_decode(envelope["supervisor_ephemeral_public_key"]))
        shared_secret = self.endpoint_private_key.exchange(supervisor_public_key)
        salt = _json_bytes(
            {
                "contract_version": BLE_PROVISIONING_CONTRACT_VERSION,
                "schema_version": "1.0",
                "onboarding_session_id": envelope["onboarding_session_id"],
                "target_node_id": envelope["target_node_id"],
                "pairing_nonce": envelope["pairing_nonce"],
            }
        )
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=f"hexe:{BLE_PROVISIONING_KEY_AGREEMENT}:ble.provision_wifi".encode("ascii"),
        ).derive(shared_secret)
        aad = _b64url_decode(envelope["aad"])
        ciphertext = _b64url_decode(envelope["ciphertext"]) + _b64url_decode(envelope["tag"])
        decrypted = AESGCM(key).decrypt(_b64url_decode(envelope["nonce"]), ciphertext, aad)
        return json.loads(decrypted)


if __name__ == "__main__":
    unittest.main()
