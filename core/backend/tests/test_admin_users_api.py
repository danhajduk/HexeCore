import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin import configure_admin_users_store, router as admin_router
from app.system.users import UsersStore, build_users_router


class TestAdminUsersApi(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "users.db")
        self.users_store = UsersStore(self.db_path)

        self.env_patch = patch.dict(
            os.environ,
            {
                "SYNTHIA_ADMIN_TOKEN": "test-token",
                "SYNTHIA_ADMIN_SESSION_SECRET": "test-session-secret",
                "SYNTHIA_ADMIN_COOKIE_SECURE": "0",
            },
            clear=False,
        )
        self.env_patch.start()

        app = FastAPI()
        configure_admin_users_store(self.users_store)
        app.include_router(admin_router, prefix="/api")
        app.include_router(build_users_router(self.users_store), prefix="/api/admin")
        self.client = TestClient(app)

        with self.client:
            pass

        import asyncio

        asyncio.run(self.users_store.ensure_admin_user("admin", "admin-pass"))

    def tearDown(self) -> None:
        configure_admin_users_store(None)
        self.env_patch.stop()
        self.tempdir.cleanup()

    def _login_as_admin(self) -> None:
        res = self.client.post(
            "/api/admin/session/login-user",
            json={"username": "admin", "password": "admin-pass"},
        )
        self.assertEqual(res.status_code, 200, res.text)

    def test_login_user_rejects_non_admin(self) -> None:
        import asyncio

        asyncio.run(
            self.users_store.upsert_user(
                username="guest1",
                role="guest",
                enabled=True,
                password="guest-pass",
            )
        )
        res = self.client.post(
            "/api/admin/session/login-user",
            json={"username": "guest1", "password": "guest-pass"},
        )
        self.assertEqual(res.status_code, 403, res.text)

    def test_users_crud_and_last_admin_guard(self) -> None:
        unauthorized = self.client.get("/api/admin/users")
        self.assertEqual(unauthorized.status_code, 401, unauthorized.text)

        self._login_as_admin()

        listed = self.client.get("/api/admin/users")
        self.assertEqual(listed.status_code, 200, listed.text)
        usernames = [item["username"] for item in listed.json().get("items", [])]
        self.assertIn("admin", usernames)

        create_user = self.client.post(
            "/api/admin/users",
            json={
                "username": "alice",
                "password": "alice-pass",
                "role": "admin",
                "enabled": True,
            },
        )
        self.assertEqual(create_user.status_code, 200, create_user.text)

        disable_admin = self.client.post(
            "/api/admin/users",
            json={"username": "admin", "role": "guest", "enabled": False},
        )
        self.assertEqual(disable_admin.status_code, 200, disable_admin.text)

        delete_last_admin = self.client.delete("/api/admin/users/alice")
        self.assertEqual(delete_last_admin.status_code, 400, delete_last_admin.text)
        self.assertIn("last_enabled_admin_required", delete_last_admin.text)


if __name__ == "__main__":
    unittest.main()
