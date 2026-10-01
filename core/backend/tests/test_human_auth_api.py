import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.system.auth import ServiceTokenKeyStore, build_human_auth_router
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
        self.keys = ServiceTokenKeyStore(_Settings())
        asyncio.run(self.users.ensure_admin_user("Dan", "owner-pass"))
        asyncio.run(self.users.ensure_admin_user("admin", "admin-pass"))
        asyncio.run(self.users.migrate_initial_owner("Dan", "0123456789abcdef"))
        asyncio.run(self.users.upsert_user(username="member", role="member", enabled=True, password="member-pass"))
        app = FastAPI()
        app.include_router(build_human_auth_router(self.keys, self.users), prefix="/api/auth")
        app.include_router(build_users_router(self.users, key_store=self.keys), prefix="/api/admin")
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
            json={"username": "member", "role": "guest", "enabled": True},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        stale = self.client.get("/api/auth/user/sessions", headers={"Authorization": f"Bearer {member['access_token']}"})
        self.assertEqual(stale.status_code, 401, stale.text)

    def test_last_owner_cannot_be_disabled(self):
        owner = self.login("Dan", "owner-pass")
        response = self.client.post(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {owner['access_token']}"},
            json={"username": "Dan", "role": "owner", "enabled": False},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("last_enabled_owner_required", response.text)


if __name__ == "__main__":
    unittest.main()
