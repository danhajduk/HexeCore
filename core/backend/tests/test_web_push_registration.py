import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.web_push_registration import WebPushRegistrationGrantIssuer, build_web_push_registration_router, verify_registration_grant
from app.system.auth import ServiceTokenKeyStore, WebAppEnrollmentStore, build_human_auth_router
from app.system.settings.store import SettingsStore
from app.system.users import UsersStore


class TestWebPushRegistration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.core_id = "0123456789abcdef"
        self.env = patch.dict(os.environ, {"HEXE_CORE_ID": self.core_id, "PLATFORM_DOMAIN": "hexe-ai.com"}, clear=False)
        self.env.start()
        path = os.path.join(self.tmp.name, "users.db")
        self.settings = SettingsStore(os.path.join(self.tmp.name, "settings.db"))
        asyncio.run(self.settings.set("platform.core_id", self.core_id))
        asyncio.run(self.settings.set("core.id", self.core_id))
        self.users, self.devices, self.keys = UsersStore(path), WebAppEnrollmentStore(path), ServiceTokenKeyStore(self.settings)
        self.alice = asyncio.run(self.users.upsert_user(username="Alice", role="member", enabled=True, password="alice-pass"))
        self.bob = asyncio.run(self.users.upsert_user(username="Bob", role="member", enabled=True, password="bob-pass"))
        now = datetime.now(timezone.utc).isoformat()
        self.devices._conn.execute("INSERT INTO web_app_devices VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)", ("alice-phone", self.core_id, self.alice["user_id"], "Phone", "public-key", "test", now, now))
        self.devices._conn.execute("INSERT INTO web_app_device_state VALUES (?, 1, ?, '{}', ?)", ("alice-phone", now, now))
        self.issuer = WebPushRegistrationGrantIssuer(self.settings, gateway_url="https://push.example/v1/subscriptions", gateway_audience="gateway-test", vapid_public_key="vapid-public", ttl_seconds=120)
        app = FastAPI()
        app.include_router(build_human_auth_router(self.keys, self.users), prefix="/api/auth")
        app.include_router(build_web_push_registration_router(self.issuer, self.keys, self.users, self.devices, self.settings), prefix="/api/web-app")
        self.client = TestClient(app)
        login = self.client.post("/api/auth/user/login", json={"username": "Alice", "password": "alice-pass", "device_id": "alice-phone"}).json()
        self.auth = {"Authorization": f"Bearer {login['access_token']}"}

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_config_and_device_bound_registration_grant(self):
        config = self.client.get("/api/web-app/notification-subscriptions/config", headers=self.auth)
        self.assertEqual(config.status_code, 200, config.text)
        self.assertEqual(config.json()["gateway_url"], "https://push.example/v1/subscriptions")
        response = self.client.post("/api/web-app/notification-subscriptions/grants", headers=self.auth, json={"operation": "register"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        seen = set()
        claims = verify_registration_grant(body["grant"], config.json()["grant_public_key"], core_id=self.core_id, user_id=self.alice["user_id"], device_id="alice-phone", audience="gateway-test", operation="register", seen_jtis=seen)
        self.assertEqual(claims["device_id"], "alice-phone")
        with self.assertRaisesRegex(ValueError, "replayed"):
            verify_registration_grant(body["grant"], config.json()["grant_public_key"], core_id=self.core_id, user_id=self.alice["user_id"], device_id="alice-phone", audience="gateway-test", operation="register", seen_jtis=seen)

    def test_wrong_core_user_device_audience_operation_and_expiry_fail(self):
        grant, claims = asyncio.run(self.issuer.issue(core_id=self.core_id, user_id=self.alice["user_id"], device_id="alice-phone", operation="register"))
        public = asyncio.run(self.issuer.public_key())
        base = dict(core_id=self.core_id, user_id=self.alice["user_id"], device_id="alice-phone", audience="gateway-test", operation="register")
        for key, value in (("core_id", "other"), ("user_id", self.bob["user_id"]), ("device_id", "other-phone"), ("audience", "other-gateway"), ("operation", "delete")):
            changed = {**base, key: value}
            with self.assertRaisesRegex(ValueError, "claims"):
                verify_registration_grant(grant, public, seen_jtis=set(), **changed)
        with self.assertRaisesRegex(ValueError, "expired"):
            verify_registration_grant(grant, public, seen_jtis=set(), now=int(claims["exp"]), **base)

    def test_cross_user_token_and_delete_without_subscription_are_denied(self):
        bob_login = self.client.post("/api/auth/user/login", json={"username": "Bob", "password": "bob-pass", "device_id": "alice-phone"}).json()
        denied = self.client.post("/api/web-app/notification-subscriptions/grants", headers={"Authorization": f"Bearer {bob_login['access_token']}"}, json={"operation": "register"})
        self.assertEqual(denied.status_code, 403, denied.text)
        absent = self.client.post("/api/web-app/notification-subscriptions/grants", headers=self.auth, json={"operation": "delete"})
        self.assertEqual(absent.status_code, 409, absent.text)
        now = datetime.now(timezone.utc).isoformat()
        self.devices._conn.execute("INSERT INTO web_app_notification_subscriptions VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'active')", ("alice-phone", self.core_id, self.alice["user_id"], "opaque-ref", "gateway-test", now, now))
        deletion = self.client.post("/api/web-app/notification-subscriptions/grants", headers=self.auth, json={"operation": "delete"})
        self.assertEqual(deletion.status_code, 200, deletion.text)
        self.assertEqual(deletion.json()["subscription_ref"], "opaque-ref")

    def test_unconfigured_and_invalid_gateway_fail_closed(self):
        issuer = WebPushRegistrationGrantIssuer(self.settings, gateway_url="http://push.example", gateway_audience="gateway-test", vapid_public_key="vapid")
        self.assertFalse(issuer.configured)


if __name__ == "__main__":
    unittest.main()
