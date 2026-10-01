import asyncio
import os
import tempfile
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.system.auth import ServiceTokenKeyStore, WebAppEnrollmentStore, build_human_auth_router, build_web_app_router
from app.system.settings.store import SettingsStore
from app.system.users import UsersStore


class TestWebAppBootstrap:
    def setup_method(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {"HEXE_CORE_ID": "0123456789abcdef", "PLATFORM_DOMAIN": "hexe-ai.com"},
            clear=False,
        )
        self.env.start()
        base = self.tmp.name
        self.settings = SettingsStore(os.path.join(base, "settings.db"))
        self.users = UsersStore(os.path.join(base, "users.db"))
        self.devices = WebAppEnrollmentStore(os.path.join(base, "users.db"))
        self.keys = ServiceTokenKeyStore(self.settings)
        asyncio.run(self.users.upsert_user(username="member", role="member", enabled=True, password="member-pass"))
        self.user = asyncio.run(self.users.get_user("member"))
        app = FastAPI()
        app.include_router(build_human_auth_router(self.keys, self.users), prefix="/api/auth")
        app.include_router(build_web_app_router(self.keys, self.users, self.devices, self.settings), prefix="/api/web-app")
        self.client = TestClient(app)

    def teardown_method(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def _login(self, device_id: str | None = None) -> dict:
        response = self.client.post(
            "/api/auth/user/login",
            json={"username": "member", "password": "member-pass", "device_id": device_id},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def _enroll_device(self, device_id: str = "device-123") -> None:
        now = "2026-09-30T00:00:00+00:00"
        self.devices._conn.execute(
            "INSERT INTO web_app_devices VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (device_id, "0123456789abcdef", self.user["user_id"], "Dan's phone", "public-key", "mobile", now, now),
        )

    def test_returns_safe_bootstrap_for_enrolled_session_device(self) -> None:
        self._enroll_device()
        login = self._login("device-123")
        response = self.client.get(
            "/api/web-app/bootstrap",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["core"]["core_id"] == "0123456789abcdef"
        assert payload["user"]["permissions"] == ["sessions.self"]
        assert payload["device"] == {
            "device_id": "device-123",
            "display_name": "Dan's phone",
            "platform": "mobile",
        }
        assert payload["features"]["administration"] is False
        assert payload["notifications"] == {"supported": False, "state": "not_implemented"}
        assert "public_key" not in str(payload)

    def test_fails_closed_without_access_token(self) -> None:
        response = self.client.get("/api/web-app/bootstrap")
        assert response.status_code == 401
        assert response.json()["detail"] == "human_access_token_missing"

    def test_fails_closed_for_session_without_enrolled_device(self) -> None:
        login = self._login()
        response = self.client.get(
            "/api/web-app/bootstrap",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "enrolled_device_required"

    def test_fails_closed_for_device_owned_by_another_user(self) -> None:
        self._enroll_device()
        self.devices._conn.execute(
            "UPDATE web_app_devices SET user_id = ? WHERE device_id = ?",
            ("usr_someone_else", "device-123"),
        )
        login = self._login("device-123")
        response = self.client.get(
            "/api/web-app/bootstrap",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "enrolled_device_invalid"

    def test_fails_closed_for_revoked_device(self) -> None:
        self._enroll_device()
        self.devices._conn.execute(
            "UPDATE web_app_devices SET revoked_at = ? WHERE device_id = ?",
            ("2026-09-30T01:00:00+00:00", "device-123"),
        )
        login = self._login("device-123")
        response = self.client.get(
            "/api/web-app/bootstrap",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "enrolled_device_invalid"

    def test_fails_closed_for_device_from_another_core(self) -> None:
        self._enroll_device()
        self.devices._conn.execute(
            "UPDATE web_app_devices SET core_id = ? WHERE device_id = ?",
            ("fedcba9876543210", "device-123"),
        )
        login = self._login("device-123")
        response = self.client.get(
            "/api/web-app/bootstrap",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "enrolled_device_wrong_core"
