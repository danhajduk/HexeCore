import asyncio
import base64
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.web_notification_policy import NotificationIntentStore
from app.core.web_push_gateway import WebPushGatewayPublisher
from app.core.web_push_gateway import build_web_push_gateway_router
from app.system.auth import ServiceTokenKeyStore, build_human_auth_router
from app.system.auth.device_enrollment import WebAppEnrollmentStore
from app.system.settings.store import SettingsStore
from app.system.users import UsersStore


class TestWebPushGateway(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        users_path = os.path.join(self.tmp.name, "users.db")
        self.users = UsersStore(users_path)
        self.devices = WebAppEnrollmentStore(users_path)
        self.intents = NotificationIntentStore(users_path)
        self.settings = SettingsStore(os.path.join(self.tmp.name, "settings.db"))
        self.user = asyncio.run(self.users.upsert_user(username="Alice", role="member", enabled=True, password="alice-pass"))
        now = datetime.now(timezone.utc).isoformat()
        self.devices._conn.execute("INSERT INTO web_app_devices VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)", ("alice-phone", "core-test", self.user["user_id"], "Phone", "public-key", "test", now, now))
        self.devices._conn.execute("INSERT INTO web_app_notification_subscriptions VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'active')", ("alice-phone", "core-test", self.user["user_id"], "sub_opaque", "gateway-test", now, now))
        asyncio.run(self.settings.set("gateway-credential", {"core_id": "core-test", "scopes": ["notification.publish"], "secret": "s" * 48}))

    def tearDown(self): self.tmp.cleanup()

    def add_intent(self, event_id="evt-1"):
        now = datetime.now(timezone.utc).isoformat()
        asyncio.run(self.intents.create({"event_id": event_id, "core_id": "core-test", "user_id": self.user["user_id"], "device_id": "alice-phone", "subscription_ref": "sub_opaque", "gateway_audience": "gateway-test", "category": "task-completion", "severity": "info", "privacy_level": "generic", "title": "Task update", "body": "Open Hexe to view details.", "navigation_path": "/app/tasks", "created_at": now}))

    def publisher(self, handler, max_attempts=8):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return WebPushGatewayPublisher(self.intents, self.devices, self.settings, core_id="core-test", gateway_url="https://gateway.example", credential_ref="gateway-credential", audience="gateway-test", client=client, max_attempts=max_attempts)

    def test_signed_idempotent_contract_and_acceptance(self):
        self.add_intent()
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(202)
        result = asyncio.run(self.publisher(handler).publish_due(now=datetime(2026, 10, 1, tzinfo=timezone.utc)))
        self.assertEqual(result["accepted"], 1)
        request = requests[0]
        self.assertTrue(request.headers["Authorization"].startswith("HexeAssertion "))
        self.assertEqual(request.headers["Idempotency-Key"], f"core-test:evt-1:alice-phone:task-completion")
        body = json.loads(request.content)
        self.assertEqual(body["core_id"], "core-test")
        self.assertEqual(body["subscription_ref"], "sub_opaque")
        self.assertNotIn("secret", request.content.decode())
        assertion = request.headers["Authorization"].split(" ", 1)[1].split(".", 1)[0]
        claims = json.loads(base64.urlsafe_b64decode(assertion + "=" * (-len(assertion) % 4)))
        self.assertEqual(claims["aud"], "gateway-test")
        self.assertEqual(claims["scp"], ["notification.publish"])
        self.assertTrue(claims["jti"])
        self.assertEqual(claims["body_sha256"], hashlib.sha256(request.content).hexdigest())

    def test_retry_dead_letter_and_restart_persistence(self):
        self.add_intent()
        retry = asyncio.run(self.publisher(lambda request: httpx.Response(503), max_attempts=2).publish_due())
        self.assertEqual(retry["retry"], 1)
        row = self.intents._conn.execute("SELECT * FROM web_app_notification_intents").fetchone()
        self.assertEqual(row["status"], "retry")
        self.intents._conn.execute("UPDATE web_app_notification_intents SET next_attempt_at=NULL")
        restarted = NotificationIntentStore(os.path.join(self.tmp.name, "users.db"))
        publisher = WebPushGatewayPublisher(restarted, self.devices, self.settings, core_id="core-test", gateway_url="https://gateway.example", credential_ref="gateway-credential", audience="gateway-test", client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(503))), max_attempts=2)
        self.assertEqual(asyncio.run(publisher.publish_due())["dead"], 1)

    def test_invalid_subscription_cleans_only_target(self):
        self.add_intent()
        result = asyncio.run(self.publisher(lambda request: httpx.Response(410)).publish_due())
        self.assertEqual(result["invalid_subscription"], 1)
        row = self.devices._conn.execute("SELECT deleted_at, cleanup_state FROM web_app_notification_subscriptions WHERE device_id='alice-phone'").fetchone()
        self.assertIsNotNone(row["deleted_at"])
        self.assertEqual(row["cleanup_state"], "pending")
        self.assertIsNone(asyncio.run(self.devices.get_device("alice-phone"))["revoked_at"])

    def test_revocation_cleanup_is_authenticated_and_idempotent(self):
        asyncio.run(self.devices.delete_notification_subscription(device_id="alice-phone", core_id="core-test", user_id=self.user["user_id"]))
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(204)
        publisher = self.publisher(handler)
        result = asyncio.run(publisher.cleanup_due(now=datetime(2026, 10, 2, tzinfo=timezone.utc)))
        self.assertEqual(result["deleted"], 1)
        request = requests[0]
        self.assertEqual(request.method, "DELETE")
        assertion = request.headers["Authorization"].split(" ", 1)[1].split(".", 1)[0]
        claims = json.loads(base64.urlsafe_b64decode(assertion + "=" * (-len(assertion) % 4)))
        self.assertEqual(claims["scp"], ["notification.subscription.delete"])
        self.assertEqual(claims["body_sha256"], hashlib.sha256(b"").hexdigest())
        self.assertEqual(asyncio.run(publisher.cleanup_due())["deleted"], 0)

    def test_cleanup_gateway_outage_remains_pending(self):
        asyncio.run(self.devices.delete_notification_subscription(device_id="alice-phone", core_id="core-test", user_id=self.user["user_id"]))
        result = asyncio.run(self.publisher(lambda request: httpx.Response(503)).cleanup_due())
        self.assertEqual(result["retry"], 1)
        row = self.devices._conn.execute("SELECT cleanup_state FROM web_app_notification_subscriptions WHERE device_id='alice-phone'").fetchone()
        self.assertEqual(row["cleanup_state"], "pending")

    def test_wrong_core_or_scope_credential_fails_closed(self):
        self.add_intent()
        asyncio.run(self.settings.set("gateway-credential", {"core_id": "other", "scopes": ["notification.publish"], "secret": "s" * 48}))
        publisher = self.publisher(lambda request: self.fail("gateway must not be called"))
        self.assertFalse(asyncio.run(publisher.safe_status())["configured"])
        self.assertEqual(asyncio.run(publisher.publish_due())["accepted"], 0)

    def test_rate_limit_retries_and_auth_failure_is_permanent(self):
        self.add_intent("evt-rate")
        self.assertEqual(asyncio.run(self.publisher(lambda request: httpx.Response(429)).publish_due())["retry"], 1)
        self.intents._conn.execute("UPDATE web_app_notification_intents SET status='pending', next_attempt_at=NULL")
        self.assertEqual(asyncio.run(self.publisher(lambda request: httpx.Response(401)).publish_due())["dead"], 1)
        row = self.intents._conn.execute("SELECT status, last_error FROM web_app_notification_intents").fetchone()
        self.assertEqual(tuple(row), ("dead", "gateway_authentication_failed"))

    def test_status_is_sanitized_and_requires_user_management_permission(self):
        asyncio.run(self.users.upsert_user(username="Owner", role="owner", enabled=True, password="owner-pass"))
        keys = ServiceTokenKeyStore(self.settings)
        publisher = self.publisher(lambda request: httpx.Response(202))
        app = FastAPI()
        app.include_router(build_human_auth_router(keys, self.users), prefix="/api/auth")
        app.include_router(build_web_push_gateway_router(publisher, keys, self.users), prefix="/api/web-app")
        client = TestClient(app)
        member = client.post("/api/auth/user/login", json={"username": "Alice", "password": "alice-pass"}).json()
        owner = client.post("/api/auth/user/login", json={"username": "Owner", "password": "owner-pass"}).json()
        self.assertEqual(client.get("/api/web-app/notification-gateway/status", headers={"Authorization": f"Bearer {member['access_token']}"}).status_code, 403)
        response = client.get("/api/web-app/notification-gateway/status", headers={"Authorization": f"Bearer {owner['access_token']}"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("gateway.example", response.text)
        self.assertNotIn("sub_opaque", response.text)
        self.assertNotIn("credential", response.text)
        denied = client.post(
            "/api/web-app/notification-gateway/credential/rotate",
            headers={"Authorization": f"Bearer {member['access_token']}"},
            json={"password": "alice-pass", "secret": "n" * 48},
        )
        self.assertEqual(denied.status_code, 403, denied.text)
        wrong_password = client.post(
            "/api/web-app/notification-gateway/credential/rotate",
            headers={"Authorization": f"Bearer {owner['access_token']}"},
            json={"password": "wrong", "secret": "n" * 48},
        )
        self.assertEqual(wrong_password.status_code, 403, wrong_password.text)
        rotated = client.post(
            "/api/web-app/notification-gateway/credential/rotate",
            headers={"Authorization": f"Bearer {owner['access_token']}"},
            json={"password": "owner-pass", "secret": "n" * 48},
        )
        self.assertEqual(rotated.status_code, 200, rotated.text)
        self.assertNotIn("n" * 16, rotated.text)


if __name__ == "__main__": unittest.main()
