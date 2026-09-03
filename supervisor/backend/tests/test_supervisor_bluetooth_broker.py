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
from app.system.hardware import (
    BLE_PAIRING_ADVERT_OPERATION,
    BLE_PAIRING_ADVERT_SCOPE,
    BLE_PROVISIONING_CONTRACT_VERSION,
    BLE_PROVISIONING_KEY_AGREEMENT,
    HARDWARE_LEASE_AUDIENCE,
    VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID,
)


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


class _PairingAdvertBackend:
    def __init__(self) -> None:
        self.started: list[dict] = []
        self.stopped: list[dict] = []

    def start_pairing_advert(self, *, adapter, pairing_offer, timeout_s):
        self.started.append({"adapter": dict(adapter), "pairing_offer": dict(pairing_offer), "timeout_s": timeout_s})
        return {"ok": True, "status": "advertising", "advertising": True}

    def stop_pairing_advert(self, *, adapter, onboarding_session_id):
        self.stopped.append({"adapter": dict(adapter), "onboarding_session_id": onboarding_session_id})
        return {"ok": True, "status": "stopped", "advertising": False}


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

    def _pairing_session_token(
        self,
        *,
        onboarding_session_id: str = "blepair-test",
        session_hint: str = "PE-123456",
        adapter: str | None = "hci0",
        supervisor_id: str = "sup-1",
    ) -> str:
        now = int(time.time())
        claims = {
            "sub": "core",
            "aud": HARDWARE_LEASE_AUDIENCE,
            "scp": [BLE_PAIRING_ADVERT_SCOPE],
            "iat": now,
            "exp": now + 600,
            "jti": "blepairtoken-test",
            "operation": BLE_PAIRING_ADVERT_OPERATION,
            "supervisor_id": supervisor_id,
            "adapter": adapter,
            "onboarding_session_id": onboarding_session_id,
            "session_hint": session_hint,
            "payload_schema_id": VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID,
        }
        return sign_hs256({"alg": "HS256", "typ": "JWT", "kid": "hardware-v1"}, claims, secret="test-hardware-secret")

    def test_ble_scan_requires_matching_lease_scope(self) -> None:
        response = self.client.post(
            "/api/supervisor/hardware/bluetooth/ble/scan",
            json={"node_id": "node-1", "lease_token": self._lease_token(operation="ble.status"), "adapter": "hci0"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["error"], "claim_scope_missing")

    def test_ble_identity_reads_onboarding_characteristics(self) -> None:
        calls: list[list[str]] = []
        connect_attempts = 0

        class _ScanProcess:
            def __init__(self, cmd, **kwargs) -> None:
                calls.append(list(cmd))
                self.returncode = None

            def poll(self):
                return self.returncode

            def terminate(self) -> None:
                self.returncode = -15

            def communicate(self, timeout=None):
                return ("[NEW] Device AA:BB:CC:DD:EE:FF HexeRecovery\n", "")

        def read_output(payload: dict) -> str:
            encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            hex_rows = " ".join(f"{value:02x}" for value in encoded)
            return f"Attempting to read ...\n[CHG] Attribute /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/service0010/char0011 Value:\n  {hex_rows}\n"

        def fake_run(cmd, **kwargs):
            nonlocal connect_attempts
            calls.append(list(cmd))
            if cmd == ["bluetoothctl", "connect", "AA:BB:CC:DD:EE:FF"]:
                connect_attempts += 1
                if connect_attempts == 1:
                    return _Completed(stdout="Device AA:BB:CC:DD:EE:FF not available\n")
                return _Completed(stdout="Connection successful\n")
            if cmd == ["bluetoothctl", "info", "AA:BB:CC:DD:EE:FF"]:
                return _Completed(stdout="Device AA:BB:CC:DD:EE:FF not available\n")
            if cmd[:2] == ["bash", "-lc"] and "bluetoothctl --timeout 20" in cmd[2]:
                return _Completed(
                    stdout=(
                        read_output(
                            {
                                "target_node_id": "hexe-pe-1",
                                "endpoint_ephemeral_public_key": self.endpoint_public_key,
                                "board_profile": "ha_voice_pe",
                                "firmware_version": "min-test",
                                "provisioning_mode": "endpoint_app",
                            }
                        )
                        + read_output(
                            {
                                "onboarding_session_id": "ble-session-1",
                                "target_node_id": "hexe-pe-1",
                                "pairing_nonce": "nonce-123456",
                                "endpoint_ephemeral_public_key": self.endpoint_public_key,
                            }
                        )
                        + read_output({"state": "advertising", "reason": "ready"})
                    )
                )
            return _Completed()

        with patch("app.supervisor.service.shutil.which", return_value="/usr/bin/bluetoothctl"):
            with patch("app.supervisor.service.subprocess.Popen", side_effect=_ScanProcess):
                with patch("app.supervisor.service.subprocess.run", side_effect=fake_run):
                    response = self.client.post(
                        "/api/supervisor/hardware/bluetooth/ble/identity",
                        json={
                        "node_id": "node-1",
                        "lease_token": self._lease_token(operation="ble.read_identity"),
                        "adapter": "hci0",
                        "target_address": "AA:BB:CC:DD:EE:FF",
                        "timeout_s": 20,
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"], "ble.read_identity")
        self.assertEqual(payload["target_address"], "AA:BB:CC:DD:EE:FF")
        self.assertEqual(payload["onboarding"]["board_profile"], "ha_voice_pe")
        self.assertEqual(payload["onboarding"]["onboarding_session_id"], "ble-session-1")
        self.assertEqual(payload["onboarding"]["pairing_nonce"], "nonce-123456")
        self.assertEqual(payload["onboarding"]["endpoint_ephemeral_public_key"], self.endpoint_public_key)
        self.assertIn("device_identity", payload["characteristics"])
        self.assertIn("pairing_nonce", payload["characteristics"])
        self.assertTrue(payload["discovery_refreshed"])
        self.assertEqual(calls[0], ["bluetoothctl", "--timeout", "20", "scan", "le"])
        self.assertEqual(calls[1], ["bluetoothctl", "connect", "AA:BB:CC:DD:EE:FF"])
        self.assertEqual(calls[2], ["bluetoothctl", "info", "AA:BB:CC:DD:EE:FF"])
        self.assertEqual(calls[3], ["bluetoothctl", "connect", "AA:BB:CC:DD:EE:FF"])
        self.assertEqual(calls[4][:2], ["bash", "-lc"])
        self.assertIn("disconnect AA:BB:CC:DD:EE:FF", calls[4][2])

    def test_ble_pairing_advert_accepts_endpoint_identity_and_stops(self) -> None:
        backend = _PairingAdvertBackend()
        self.service._ble_pairing_advert_backend = backend
        token = self._pairing_session_token()

        started = self.client.post(
            "/api/supervisor/hardware/bluetooth/ble/pairing-advert/start",
            json={
                "session_token": token,
                "adapter": "hci0",
                "onboarding_session_id": "blepair-test",
                "session_hint": "PE-123456",
                "expires_at": _future_iso(),
                "node_profile_id": "voice",
                "payload_schema_id": VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID,
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        start_payload = started.json()
        self.assertTrue(start_payload["ok"])
        self.assertEqual(start_payload["status"], "advertising")
        self.assertEqual(start_payload["pairing_offer"]["session_role"], "host_pairing_advert")
        self.assertEqual(start_payload["pairing_offer"]["payload_schema_id"], VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID)
        self.assertEqual(backend.started[0]["pairing_offer"]["onboarding_session_id"], "blepair-test")

        identity = self.client.post(
            "/api/supervisor/hardware/bluetooth/ble/pairing-advert/endpoint-identity",
            json={
                "session_token": token,
                "adapter": "hci0",
                "onboarding_session_id": "blepair-test",
                "contract_version": "1.0",
                "device_id": "hexe-pe-a0-85-e3-f0-e1-6e",
                "node_hardware_id": "A0:85:E3:F0:E1:6E",
                "target_node_id": "voice-node-a0",
                "board_profile": "ha_voice_pe",
                "firmware_version": "min-fw-test",
                "application_type": "hexe_voice",
                "provisioning_mode": "core_published_pairing",
                "endpoint_ephemeral_public_key": self.endpoint_public_key,
                "supported_payload_schemas": [VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID],
                "provisioning_state": "awaiting_credentials",
            },
        )
        self.assertEqual(identity.status_code, 200, identity.text)
        identity_payload = identity.json()
        self.assertTrue(identity_payload["ok"])
        self.assertEqual(identity_payload["status"], "endpoint_identity_received")
        self.assertEqual(identity_payload["endpoint_identity"]["device_id"], "hexe-pe-a0-85-e3-f0-e1-6e")
        self.assertEqual(identity_payload["endpoint_identity"]["board_profile"], "ha_voice_pe")

        status = self.client.post(
            "/api/supervisor/hardware/bluetooth/ble/pairing-advert/status",
            json={"session_token": token, "adapter": "hci0", "onboarding_session_id": "blepair-test"},
        )
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()["endpoint_identity"]["device_id"], "hexe-pe-a0-85-e3-f0-e1-6e")

        stopped = self.client.post(
            "/api/supervisor/hardware/bluetooth/ble/pairing-advert/stop",
            json={"session_token": token, "adapter": "hci0", "onboarding_session_id": "blepair-test", "reason": "operator closed"},
        )
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertEqual(stopped.json()["status"], "stopped")
        self.assertFalse(stopped.json()["advertising"])
        self.assertEqual(backend.stopped[0]["onboarding_session_id"], "blepair-test")

    def test_ble_scan_uses_brokered_bluetoothctl_surface(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:3] == ["bluetoothctl", "--timeout", "60"]:
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
                        "scan_seconds": 60,
                    },
                )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"], "ble.scan")
        self.assertEqual(payload["adapter"]["adapter"], "hci0")
        self.assertEqual(payload["revocation_check"], "local_token_only")
        self.assertEqual(payload["scan_transport"], "le")
        self.assertEqual({item["address"] for item in payload["devices"]}, {"AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"})
        self.assertEqual(calls[0], ["bluetoothctl", "--timeout", "60", "scan", "le"])
        self.assertEqual(calls[1], ["bluetoothctl", "devices"])

    def test_ble_scan_marks_requested_service_uuid_matches(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            if cmd[:3] == ["bluetoothctl", "--timeout", "2"]:
                return _Completed(stdout="[NEW] Device AA:BB:CC:DD:EE:FF A0-85-E3-F0-E1-6E\n")
            if cmd == ["bluetoothctl", "devices"]:
                return _Completed(stdout="Device 11:22:33:44:55:66 Thermometer\n")
            if cmd == ["bluetoothctl", "info", "AA:BB:CC:DD:EE:FF"]:
                return _Completed(
                    stdout=(
                        "Device AA:BB:CC:DD:EE:FF (public)\n"
                        "Name: Hexe Voice PE\n"
                        "Alias: A0-85-E3-F0-E1-6E\n"
                        "UUID: Vendor specific (7f9c0000-5f04-4d8b-9a46-7c0f7a100000)\n"
                    )
                )
            if cmd == ["bluetoothctl", "info", "11:22:33:44:55:66"]:
                return _Completed(
                    stdout=(
                        "Device 11:22:33:44:55:66\n"
                        "Name: Thermometer\n"
                        "UUID: Heart Rate (0000180d-0000-1000-8000-00805f9b34fb)\n"
                    )
                )
            return _Completed()

        with patch("app.supervisor.service.shutil.which", return_value="/usr/bin/bluetoothctl"):
            with patch("app.supervisor.service.subprocess.run", side_effect=fake_run):
                response = self.client.post(
                    "/api/supervisor/hardware/bluetooth/ble/scan",
                    json={
                        "node_id": "node-1",
                        "lease_token": self._lease_token(),
                        "adapter": "hci0",
                        "service_uuid": "{7F9C0000-5F04-4D8B-9A46-7C0F7A100000}",
                        "scan_seconds": 2,
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["service_uuid"], "7f9c0000-5f04-4d8b-9a46-7c0f7a100000")
        self.assertEqual([item["address"] for item in payload["matching_devices"]], ["AA:BB:CC:DD:EE:FF"])
        matched = payload["matching_devices"][0]
        self.assertTrue(matched["service_uuid_match"])
        self.assertEqual(matched["matched_service_uuid"], "7f9c0000-5f04-4d8b-9a46-7c0f7a100000")
        self.assertEqual(matched["uuids"], ["7f9c0000-5f04-4d8b-9a46-7c0f7a100000"])
        self.assertEqual(calls[2], ["bluetoothctl", "info", "AA:BB:CC:DD:EE:FF"])
        self.assertEqual(calls[3], ["bluetoothctl", "info", "11:22:33:44:55:66"])

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
