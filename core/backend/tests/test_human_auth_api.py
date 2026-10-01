import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.system.auth import ServiceTokenKeyStore, WebAppEnrollmentStore, build_human_auth_router
from app.system.users import UsersStore, build_users_router


class _Settings:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = value
        return value


class TestHumanAuthApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"HEXE_CORE_ID": "0123456789abcdef", "HEXE_ADMIN_TOKEN": "bootstrap"}, clear=False)
        self.env.start()
        self.users = UsersStore(os.path.join(self.tmp.name, "users.db"))
        self.devices = WebAppEnrollmentStore(os.path.join(self.tmp.name, "users.db"))
        self.keys = ServiceTokenKeyStore(_Settings())
        asyncio.run(self.users.ensure_admin_user("Dan", "owner-pass"))
        asyncio.run(self.users.ensure_admin_user("admin", "admin-pass"))
        asyncio.run(self.users.migrate_initial_owner("Dan", "0123456789abcdef"))
        asyncio.run(self.users.upsert_user(username="member", role="member", enabled=True, password="member-pass"))
        app = FastAPI()
        app.include_router(build_human_auth_router(self.keys, self.users), prefix="/api/auth")
        app.include_router(build_users_router(self.users, key_store=self.keys, devices_store=self.devices), prefix="/api/admin")
        self.client = TestClient(app)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def login(self, username, password):
        response = self.client.post("/api/auth/user/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_owner_migration_preserves_password_and_seeded_admin(self):
        owner = self.login("Dan", "owner-pass")
        admin = self.login("admin", "admin-pass")
        self.assertEqual(owner["user"]["role"], "owner")
        self.assertEqual(admin["user"]["role"], "admin")
        self.assertNotEqual(owner["user"]["user_id"], admin["user"]["user_id"])

    def test_access_claims_refresh_rotation_and_reuse_revocation(self):
        login = self.login("member", "member-pass")
        claims = login["claims"]
        self.assertEqual(claims["iss"], "hexe-core:0123456789abcdef")
        self.assertEqual(claims["aud"], "hexe-core:0123456789abcdef:web-app")
        self.assertEqual(claims["sub"], login["user"]["user_id"])
        self.assertTrue(claims["session_id"])
        rotated = self.client.post("/api/auth/user/refresh", json={"refresh_token": login["refresh_token"]})
        self.assertEqual(rotated.status_code, 200, rotated.text)
        replay = self.client.post("/api/auth/user/refresh", json={"refresh_token": login["refresh_token"]})
        self.assertEqual(replay.status_code, 401, replay.text)
        rejected = self.client.get("/api/auth/user/sessions", headers={"Authorization": f"Bearer {rotated.json()['access_token']}"})
        self.assertEqual(rejected.status_code, 401, rejected.text)

    def test_member_cannot_administer_users_and_revocation_is_isolated(self):
        member = self.login("member", "member-pass")
        owner = self.login("Dan", "owner-pass")
        denied = self.client.get("/api/admin/users", headers={"Authorization": f"Bearer {member['access_token']}"})
        self.assertEqual(denied.status_code, 403, denied.text)
        member_logout = self.client.post("/api/auth/user/logout", headers={"Authorization": f"Bearer {member['access_token']}"})
        self.assertEqual(member_logout.status_code, 200, member_logout.text)
        owner_sessions = self.client.get("/api/auth/user/sessions", headers={"Authorization": f"Bearer {owner['access_token']}"})
        self.assertEqual(owner_sessions.status_code, 200, owner_sessions.text)

    def test_role_change_invalidates_existing_access(self):
        member = self.login("member", "member-pass")
        owner = self.login("Dan", "owner-pass")
        changed = self.client.post(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {owner['access_token']}"},
            json={"username": "member", "role": "guest", "enabled": True, "reauth_password": "owner-pass"},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        stale = self.client.get("/api/auth/user/sessions", headers={"Authorization": f"Bearer {member['access_token']}"})
        self.assertEqual(stale.status_code, 401, stale.text)

    def test_last_owner_cannot_be_disabled(self):
        owner = self.login("Dan", "owner-pass")
        response = self.client.post(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {owner['access_token']}"},
            json={"username": "Dan", "role": "owner", "enabled": False, "reauth_password": "owner-pass"},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("last_enabled_owner_required", response.text)

    def test_user_disablement_revokes_sessions_and_queues_only_owned_device_cleanup(self):
        member = asyncio.run(self.users.get_user("member"))
        owner = asyncio.run(self.users.get_user("Dan"))
        now = "2026-10-01T00:00:00+00:00"
        for device_id, user_id in (("member-phone", member["user_id"]), ("owner-phone", owner["user_id"])):
            self.devices._conn.execute(
                "INSERT INTO web_app_devices VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (device_id, "0123456789abcdef", user_id, device_id, "public-key", "test", now, now),
            )
            self.devices._conn.execute(
                "INSERT INTO web_app_notification_subscriptions VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'active')",
                (device_id, "0123456789abcdef", user_id, f"sub_{device_id}", "hexe-notification-gateway", now, now),
            )
        member_login = self.login("member", "member-pass")
        owner_login = self.login("Dan", "owner-pass")
        disabled = self.client.post(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {owner_login['access_token']}"},
            json={"username": "member", "role": "member", "enabled": False, "reauth_password": "owner-pass"},
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertEqual(disabled.json()["disabled_device_count"], 1)
        stale = self.client.get("/api/auth/user/sessions", headers={"Authorization": f"Bearer {member_login['access_token']}"})
        self.assertEqual(stale.status_code, 401, stale.text)
        member_device = asyncio.run(self.devices.get_device("member-phone"))
        owner_device = asyncio.run(self.devices.get_device("owner-phone"))
        self.assertFalse(member_device["enabled"])
        self.assertTrue(owner_device["enabled"])
        member_cleanup = self.devices._conn.execute(
            "SELECT deleted_at, cleanup_state FROM web_app_notification_subscriptions WHERE device_id='member-phone'"
        ).fetchone()
        owner_cleanup = self.devices._conn.execute(
            "SELECT deleted_at, cleanup_state FROM web_app_notification_subscriptions WHERE device_id='owner-phone'"
        ).fetchone()
        self.assertIsNotNone(member_cleanup["deleted_at"])
        self.assertEqual(member_cleanup["cleanup_state"], "pending")
        self.assertIsNone(owner_cleanup["deleted_at"])

    def test_user_deletion_disables_retained_device_record(self):
        member = asyncio.run(self.users.get_user("member"))
        now = "2026-10-01T00:00:00+00:00"
        self.devices._conn.execute(
            "INSERT INTO web_app_devices VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            ("member-phone", "0123456789abcdef", member["user_id"], "Member phone", "public-key", "test", now, now),
        )
        owner_login = self.login("Dan", "owner-pass")
        deleted = self.client.request(
            "DELETE",
            "/api/admin/users/member",
            headers={"Authorization": f"Bearer {owner_login['access_token']}"},
            json={"reauth_password": "owner-pass"},
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json()["disabled_device_count"], 1)
        self.assertFalse(asyncio.run(self.devices.get_device("member-phone"))["enabled"])


if __name__ == "__main__":
    unittest.main()
