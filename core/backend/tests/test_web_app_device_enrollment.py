import asyncio
import base64
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.system.auth import ServiceTokenKeyStore, WebAppEnrollmentStore, build_device_enrollment_router, build_human_auth_router
from app.system.auth.device_enrollment import CONTRACT_VERSION
from app.system.users import UsersStore


def b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class Settings:
    def __init__(self): self.data = {}
    async def get(self, key): return self.data.get(key)
    async def set(self, key, value): self.data[key] = value; return value


class TestWebAppDeviceEnrollment(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"HEXE_CORE_ID": "0123456789abcdef", "PLATFORM_DOMAIN": "hexe-ai.com"}, clear=False)
        self.env.start()
        path = os.path.join(self.tmp.name, "users.db")
        self.users, self.store, self.keys = UsersStore(path), WebAppEnrollmentStore(path), ServiceTokenKeyStore(Settings())
        asyncio.run(self.users.ensure_admin_user("Dan", "owner-pass"))
        asyncio.run(self.users.migrate_initial_owner("Dan", "0123456789abcdef"))
        app = FastAPI()
        app.include_router(build_human_auth_router(self.keys, self.users), prefix="/api/auth")
        app.include_router(build_device_enrollment_router(self.store, self.users, self.keys), prefix="/api/auth")
        self.client = TestClient(app)
        login = self.client.post("/api/auth/user/login", json={"username": "Dan", "password": "owner-pass"}).json()
        self.auth = {"Authorization": f"Bearer {login['access_token']}"}

    def tearDown(self):
        self.env.stop(); self.tmp.cleanup()

    def create_approved(self):
        created = self.client.post("/api/auth/device-enrollments", headers=self.auth, json={"display_name": "Phone"})
        self.assertEqual(created.status_code, 200, created.text)
        enrollment = created.json()["enrollment"]
        approved = self.client.post(f"/api/auth/device-enrollments/{enrollment['enrollment_id']}/approve", headers=self.auth)
        self.assertEqual(approved.status_code, 200, approved.text)
        return enrollment

    def complete(self, enrollment, private_key, device_id="device-phone-1", proof=None):
        public = b64(private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        message = f"{CONTRACT_VERSION}:0123456789abcdef:{enrollment['enrollment_id']}:{device_id}"
        return self.client.post(f"/api/auth/device-enrollments/{enrollment['enrollment_id']}/complete", json={"proof": proof or enrollment["proof"], "device_id": device_id, "public_key": public, "signature": b64(private_key.sign(message.encode())), "platform": "test"})

    def test_discovery_is_safe_and_enrollment_is_single_use(self):
        discovery = self.client.get("/api/auth/web-app/discovery")
        self.assertEqual(discovery.status_code, 200)
        self.assertEqual(set(discovery.json()), {"contract_version", "core_id", "public_hostname", "enrollment_supported"})
        enrollment = self.create_approved()
        complete = self.complete(enrollment, Ed25519PrivateKey.generate())
        self.assertEqual(complete.status_code, 200, complete.text)
        self.assertEqual(complete.json()["claims"]["device_id"], "device-phone-1")
        replay = self.complete(enrollment, Ed25519PrivateKey.generate())
        self.assertEqual(replay.status_code, 409, replay.text)

    def test_wrong_proof_and_key_possession_fail_closed(self):
        enrollment = self.create_approved()
        key = Ed25519PrivateKey.generate()
        wrong_proof = self.complete(enrollment, key, proof="x" * 48)
        self.assertEqual(wrong_proof.status_code, 409, wrong_proof.text)
        other = Ed25519PrivateKey.generate()
        public = b64(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        response = self.client.post(f"/api/auth/device-enrollments/{enrollment['enrollment_id']}/complete", json={"proof": enrollment["proof"], "device_id": "device-phone-1", "public_key": public, "signature": b64(other.sign(b"wrong-message"))})
        self.assertEqual(response.status_code, 403, response.text)

    def test_cancelled_enrollment_cannot_complete(self):
        enrollment = self.create_approved()
        cancelled = self.client.post(f"/api/auth/device-enrollments/{enrollment['enrollment_id']}/cancel", headers=self.auth)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        response = self.complete(enrollment, Ed25519PrivateKey.generate())
        self.assertEqual(response.status_code, 409, response.text)

    def test_bound_device_can_rotate_key_with_dual_proof(self):
        enrollment = self.create_approved()
        old_key, new_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        completed = self.complete(enrollment, old_key)
        token = completed.json()["access_token"]
        new_public = b64(new_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        message = f"{CONTRACT_VERSION}:rotate:0123456789abcdef:device-phone-1:{new_public}".encode()
        rotated = self.client.post("/api/auth/devices/device-phone-1/rotate-key", headers={"Authorization": f"Bearer {token}"}, json={"new_public_key": new_public, "old_key_signature": b64(old_key.sign(message)), "new_key_signature": b64(new_key.sign(message))})
        self.assertEqual(rotated.status_code, 200, rotated.text)

    def test_expired_enrollment_fails_and_reports_expired(self):
        enrollment = self.create_approved()
        db = sqlite3.connect(os.path.join(self.tmp.name, "users.db"))
        db.execute("UPDATE web_app_enrollments SET expires_at=? WHERE enrollment_id=?", ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), enrollment["enrollment_id"]))
        db.commit(); db.close()
        status = self.client.get(f"/api/auth/device-enrollments/{enrollment['enrollment_id']}", headers=self.auth)
        self.assertEqual(status.json()["status"], "expired")
        response = self.complete(enrollment, Ed25519PrivateKey.generate())
        self.assertEqual(response.status_code, 409, response.text)

    def test_recovery_enrollment_revokes_replaced_device_session(self):
        first = self.create_approved()
        first_complete = self.complete(first, Ed25519PrivateKey.generate())
        old_token = first_complete.json()["access_token"]
        created = self.client.post("/api/auth/device-enrollments", headers=self.auth, json={"display_name": "Replacement", "replace_device_id": "device-phone-1"}).json()["enrollment"]
        self.client.post(f"/api/auth/device-enrollments/{created['enrollment_id']}/approve", headers=self.auth)
        replaced = self.complete(created, Ed25519PrivateKey.generate(), device_id="device-phone-2")
        self.assertEqual(replaced.status_code, 200, replaced.text)
        old_session = self.client.get("/api/auth/user/sessions", headers={"Authorization": f"Bearer {old_token}"})
        self.assertEqual(old_session.status_code, 401, old_session.text)

    def test_user_can_list_rename_and_revoke_own_device_without_public_key(self):
        enrollment = self.create_approved()
        completed = self.complete(enrollment, Ed25519PrivateKey.generate())
        token = completed.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        listed = self.client.get("/api/auth/devices", headers=headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["current_device_id"], "device-phone-1")
        self.assertEqual(listed.json()["items"][0]["display_name"], "Phone")
        self.assertNotIn("public_key", listed.text)

        renamed = self.client.patch(
            "/api/auth/devices/device-phone-1",
            headers=headers,
            json={"display_name": "My phone"},
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["device"]["display_name"], "My phone")

        revoked = self.client.delete("/api/auth/devices/device-phone-1", headers=headers)
        self.assertEqual(revoked.status_code, 200, revoked.text)
        stale = self.client.get("/api/auth/devices", headers=headers)
        self.assertEqual(stale.status_code, 401, stale.text)

    def test_user_cannot_rename_or_revoke_another_users_device(self):
        enrollment = self.create_approved()
        completed = self.complete(enrollment, Ed25519PrivateKey.generate())
        token = completed.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        now = datetime.now(timezone.utc).isoformat()
        db = sqlite3.connect(os.path.join(self.tmp.name, "users.db"))
        db.execute(
            "INSERT INTO web_app_devices VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            ("other-device", "0123456789abcdef", "usr-other", "Other phone", "public-key", "test", now, now),
        )
        db.commit(); db.close()

        renamed = self.client.patch(
            "/api/auth/devices/other-device",
            headers=headers,
            json={"display_name": "Stolen"},
        )
        self.assertEqual(renamed.status_code, 404, renamed.text)
        revoked = self.client.delete("/api/auth/devices/other-device", headers=headers)
        self.assertEqual(revoked.status_code, 404, revoked.text)

    def test_enrollment_enforces_user_and_core_device_limits(self):
        first = self.create_approved()
        self.assertEqual(self.complete(first, Ed25519PrivateKey.generate()).status_code, 200)
        self.store._max_devices_per_user = 1
        second = self.create_approved()
        limited = self.complete(second, Ed25519PrivateKey.generate(), device_id="device-phone-2")
        self.assertEqual(limited.status_code, 409, limited.text)
        self.assertEqual(limited.json()["detail"], "device_user_limit_reached")

        self.store._max_devices_per_user = 10
        self.store._max_devices_per_core = 1
        third = self.create_approved()
        core_limited = self.complete(third, Ed25519PrivateKey.generate(), device_id="device-phone-3")
        self.assertEqual(core_limited.status_code, 409, core_limited.text)
        self.assertEqual(core_limited.json()["detail"], "device_core_limit_reached")

    def test_replacement_is_allowed_at_device_limit(self):
        first = self.create_approved()
        self.assertEqual(self.complete(first, Ed25519PrivateKey.generate()).status_code, 200)
        self.store._max_devices_per_user = 1
        self.store._max_devices_per_core = 1
        replacement = self.client.post(
            "/api/auth/device-enrollments",
            headers=self.auth,
            json={"display_name": "Replacement", "replace_device_id": "device-phone-1"},
        ).json()["enrollment"]
        self.client.post(f"/api/auth/device-enrollments/{replacement['enrollment_id']}/approve", headers=self.auth)
        completed = self.complete(replacement, Ed25519PrivateKey.generate(), device_id="device-phone-2")
        self.assertEqual(completed.status_code, 200, completed.text)

    def test_notification_subscription_is_opaque_idempotent_and_device_bound(self):
        enrollment = self.create_approved()
        completed = self.complete(enrollment, Ed25519PrivateKey.generate())
        headers = {"Authorization": f"Bearer {completed.json()['access_token']}"}
        body = {"subscription_ref": "sub_opaque-reference-123", "gateway_audience": "hexe-notification-gateway"}

        created = self.client.put("/api/auth/devices/device-phone-1/notification-subscription", headers=headers, json=body)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertTrue(created.json()["changed"])
        self.assertNotIn(body["subscription_ref"], created.text)
        repeated = self.client.put("/api/auth/devices/device-phone-1/notification-subscription", headers=headers, json=body)
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertFalse(repeated.json()["changed"])
        wrong_device = self.client.put("/api/auth/devices/some-other-device/notification-subscription", headers=headers, json=body)
        self.assertEqual(wrong_device.status_code, 403, wrong_device.text)
        raw_endpoint = self.client.put(
            "/api/auth/devices/device-phone-1/notification-subscription",
            headers=headers,
            json={"subscription_ref": "https://push.example/secret", "gateway_audience": "hexe-notification-gateway"},
        )
        self.assertEqual(raw_endpoint.status_code, 422, raw_endpoint.text)

        deleted = self.client.delete("/api/auth/devices/device-phone-1/notification-subscription", headers=headers)
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json()["cleanup_state"], "pending")
        db = sqlite3.connect(os.path.join(self.tmp.name, "users.db"))
        row = db.execute("SELECT deleted_at, cleanup_state FROM web_app_notification_subscriptions WHERE device_id=?", ("device-phone-1",)).fetchone()
        db.close()
        self.assertIsNotNone(row[0])
        self.assertEqual(row[1], "pending")

    def test_device_revocation_marks_subscription_for_cleanup(self):
        enrollment = self.create_approved()
        completed = self.complete(enrollment, Ed25519PrivateKey.generate())
        headers = {"Authorization": f"Bearer {completed.json()['access_token']}"}
        registered = self.client.put(
            "/api/auth/devices/device-phone-1/notification-subscription",
            headers=headers,
            json={"subscription_ref": "sub_cleanup-reference-123", "gateway_audience": "hexe-notification-gateway"},
        )
        self.assertEqual(registered.status_code, 200, registered.text)
        self.assertEqual(self.client.delete("/api/auth/devices/device-phone-1", headers=headers).status_code, 200)
        db = sqlite3.connect(os.path.join(self.tmp.name, "users.db"))
        row = db.execute("SELECT deleted_at, cleanup_state FROM web_app_notification_subscriptions WHERE device_id=?", ("device-phone-1",)).fetchone()
        db.close()
        self.assertIsNotNone(row[0])
        self.assertEqual(row[1], "pending")

    def test_device_notification_preferences_have_safe_defaults_and_round_trip(self):
        enrollment = self.create_approved()
        completed = self.complete(enrollment, Ed25519PrivateKey.generate())
        headers = {"Authorization": f"Bearer {completed.json()['access_token']}"}
        url = "/api/auth/devices/device-phone-1/notification-preferences"

        defaults = self.client.get(url, headers=headers)
        self.assertEqual(defaults.status_code, 200, defaults.text)
        self.assertEqual(defaults.json()["preferences"]["privacy_level"], "generic")
        self.assertEqual(
            set(defaults.json()["preferences"]["categories"]),
            {"security", "approval-required", "task-completion", "timers-reminders", "device-health", "email-alerts"},
        )

        preferences = {
            "enabled": True,
            "categories": {
                "security": True,
                "approval-required": True,
                "task-completion": False,
                "timers-reminders": True,
                "device-health": False,
                "email-alerts": False,
            },
            "quiet_hours_start": "22:30",
            "quiet_hours_end": "07:15",
            "time_zone": "America/Los_Angeles",
            "privacy_level": "summary",
            "severity_threshold": "warning",
        }
        updated = self.client.put(url, headers=headers, json=preferences)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["preferences"], preferences)
        fetched = self.client.get(url, headers=headers)
        self.assertEqual(fetched.json()["preferences"], preferences)

    def test_notification_preferences_reject_invalid_or_cross_device_settings(self):
        enrollment = self.create_approved()
        completed = self.complete(enrollment, Ed25519PrivateKey.generate())
        headers = {"Authorization": f"Bearer {completed.json()['access_token']}"}
        url = "/api/auth/devices/device-phone-1/notification-preferences"
        defaults = self.client.get(url, headers=headers).json()["preferences"]

        incomplete = dict(defaults, quiet_hours_start="22:00")
        self.assertEqual(self.client.put(url, headers=headers, json=incomplete).status_code, 422)
        bad_zone = dict(defaults, time_zone="Not/A_Time_Zone")
        self.assertEqual(self.client.put(url, headers=headers, json=bad_zone).status_code, 422)
        bad_categories = dict(defaults, categories={"security": True})
        self.assertEqual(self.client.put(url, headers=headers, json=bad_categories).status_code, 422)
        cross_device = self.client.get("/api/auth/devices/other-device/notification-preferences", headers=headers)
        self.assertEqual(cross_device.status_code, 403, cross_device.text)


if __name__ == "__main__": unittest.main()
