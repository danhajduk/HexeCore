import asyncio
import os
import tempfile
import time
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.system.auth import (
    ServiceTokenKeyStore,
    WebAppEnrollmentStore,
    build_human_auth_router,
    build_web_app_router,
    sign_hs256,
)
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
        app.include_router(
            build_web_app_router(self.keys, self.users, self.devices, self.settings, realtime_heartbeat_s=0.05),
            prefix="/api/web-app",
        )
        self.client = TestClient(app)

    def teardown_method(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def _login(self, device_id: str | None = None) -> dict:
        return self._login_user("member", "member-pass", device_id)

    def _login_user(self, username: str, password: str, device_id: str | None = None) -> dict:
        response = self.client.post(
            "/api/auth/user/login",
            json={"username": username, "password": password, "device_id": device_id},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def _resign_access_token(self, login: dict, **claim_updates) -> str:
        key = asyncio.run(self.keys.active_key())
        claims = {**login["claims"], **claim_updates}
        return sign_hs256(
            {"alg": "HS256", "typ": "JWT", "kid": str(key["kid"])},
            claims,
            str(key["secret"]),
        )

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
        assert payload["device"]["device_id"] == "device-123"
        assert payload["device"]["display_name"] == "Dan's phone"
        assert payload["device"]["platform"] == "mobile"
        assert payload["device"]["enabled"] is True
        assert payload["device"]["last_seen_at"]
        assert payload["device"]["browser_metadata"] == {}
        assert payload["features"]["administration"] is False
        assert payload["features"]["notifications"] is True
        assert payload["notifications"] == {
            "supported": True,
            "subscription_registered": False,
            "preferences_configured": False,
            "delivery_available": False,
            "state": "subscription_required",
        }
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

    def test_fails_closed_for_disabled_device(self) -> None:
        self._enroll_device()
        login = self._login("device-123")
        asyncio.run(self.devices.set_device_enabled(device_id="device-123", core_id="0123456789abcdef", enabled=False))
        response = self.client.get(
            "/api/web-app/bootstrap",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "enrolled_device_invalid"

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

    def test_bootstrap_rejects_signed_token_for_wrong_core_audience(self) -> None:
        self._enroll_device()
        login = self._login("device-123")
        token = self._resign_access_token(login, aud="hexe-core:fedcba9876543210:web-app")
        response = self.client.get(
            "/api/web-app/bootstrap",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "human_access_token_invalid"

    def test_bootstrap_advertises_administration_only_for_admin_role(self) -> None:
        asyncio.run(self.users.upsert_user(username="owner", role="owner", enabled=True, password="owner-pass"))
        owner = asyncio.run(self.users.get_user("owner"))
        now = "2026-09-30T00:00:00+00:00"
        self.devices._conn.execute(
            "INSERT INTO web_app_devices VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            ("owner-device", "0123456789abcdef", owner["user_id"], "Owner phone", "public-key", "mobile", now, now),
        )
        login = self._login_user("owner", "owner-pass", "owner-device")
        response = self.client.get(
            "/api/web-app/bootstrap",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["features"]["administration"] is True
        assert "core.admin" in payload["user"]["permissions"]

    def test_realtime_authenticates_enrolled_device_and_handles_ping(self) -> None:
        self._enroll_device()
        login = self._login("device-123")
        with self.client.websocket_connect(
            "/api/web-app/realtime",
            headers={
                "Host": "0123456789abcdef.hexe-ai.com",
                "Origin": "https://0123456789abcdef.hexe-ai.com",
                "Authorization": f"Bearer {login['access_token']}",
            },
        ) as websocket:
            ready = websocket.receive_json()
            assert ready["type"] == "realtime.ready"
            assert ready["device_id"] == "device-123"
            websocket.send_json({"type": "ping"})
            assert websocket.receive_json() == {"type": "pong"}
            websocket.send_json({"type": "bootstrap.get"})
            snapshot = websocket.receive_json()
            assert snapshot["type"] == "core.bootstrap"
            assert snapshot["data"]["core"]["core_id"] == "0123456789abcdef"
            assert snapshot["data"]["user"]["user_id"] == self.user["user_id"]
            assert snapshot["data"]["device"]["device_id"] == "device-123"
            assert "public_key" not in str(snapshot)

    def test_realtime_rejects_credentials_in_query_string(self) -> None:
        try:
            with self.client.websocket_connect(
                "/api/web-app/realtime?access_token=secret",
                headers={"Host": "0123456789abcdef.hexe-ai.com"},
            ):
                raise AssertionError("websocket unexpectedly connected")
        except WebSocketDisconnect as exc:
            assert exc.code == 4400

    def test_realtime_rejects_disallowed_origin(self) -> None:
        self._enroll_device()
        login = self._login("device-123")
        try:
            with self.client.websocket_connect(
                "/api/web-app/realtime",
                headers={
                    "Host": "0123456789abcdef.hexe-ai.com",
                    "Origin": "https://evil.example",
                    "Authorization": f"Bearer {login['access_token']}",
                },
            ):
                raise AssertionError("websocket unexpectedly connected")
        except WebSocketDisconnect as exc:
            assert exc.code == 4403

    def test_realtime_renewal_accepts_same_device_identity(self) -> None:
        self._enroll_device()
        login = self._login("device-123")
        rotated = self.client.post("/api/auth/user/refresh", json={"refresh_token": login["refresh_token"]})
        assert rotated.status_code == 200
        with self.client.websocket_connect(
            "/api/web-app/realtime",
            headers={
                "Host": "0123456789abcdef.hexe-ai.com",
                "Origin": "https://0123456789abcdef.hexe-ai.com",
                "Authorization": f"Bearer {login['access_token']}",
            },
        ) as websocket:
            assert websocket.receive_json()["type"] == "realtime.ready"
            websocket.send_json({"type": "auth.renew", "access_token": rotated.json()["access_token"]})
            assert websocket.receive_json()["type"] == "auth.renewed"

    def test_realtime_rejects_anonymous_connection(self) -> None:
        try:
            with self.client.websocket_connect(
                "/api/web-app/realtime",
                headers={"Host": "0123456789abcdef.hexe-ai.com"},
            ):
                raise AssertionError("websocket unexpectedly connected")
        except WebSocketDisconnect as exc:
            assert exc.code == 4401

    def test_realtime_rejects_expired_and_wrong_audience_tokens(self) -> None:
        self._enroll_device()
        login = self._login("device-123")
        tokens = [
            self._resign_access_token(login, exp=int(time.time()) - 1),
            self._resign_access_token(login, aud="hexe-core:fedcba9876543210:web-app"),
        ]
        for token in tokens:
            try:
                with self.client.websocket_connect(
                    "/api/web-app/realtime",
                    headers={
                        "Host": "0123456789abcdef.hexe-ai.com",
                        "Authorization": f"Bearer {token}",
                    },
                ):
                    raise AssertionError("websocket unexpectedly connected")
            except WebSocketDisconnect as exc:
                assert exc.code == 4401

    def test_realtime_reconnects_with_same_active_identity(self) -> None:
        self._enroll_device()
        login = self._login("device-123")
        headers = {
            "Host": "0123456789abcdef.hexe-ai.com",
            "Authorization": f"Bearer {login['access_token']}",
        }
        for _ in range(2):
            with self.client.websocket_connect("/api/web-app/realtime", headers=headers) as websocket:
                ready = websocket.receive_json()
                assert ready["type"] == "realtime.ready"
                assert ready["session_id"] == login["claims"]["session_id"]

    def test_realtime_renewal_rejects_identity_switch(self) -> None:
        self._enroll_device()
        login = self._login("device-123")
        asyncio.run(self.users.upsert_user(username="other", role="member", enabled=True, password="other-pass"))
        other = asyncio.run(self.users.get_user("other"))
        now = "2026-09-30T00:00:00+00:00"
        self.devices._conn.execute(
            "INSERT INTO web_app_devices VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            ("other-device", "0123456789abcdef", other["user_id"], "Other phone", "public-key", "mobile", now, now),
        )
        other_login = self._login_user("other", "other-pass", "other-device")
        with self.client.websocket_connect(
            "/api/web-app/realtime",
            headers={
                "Host": "0123456789abcdef.hexe-ai.com",
                "Authorization": f"Bearer {login['access_token']}",
            },
        ) as websocket:
            assert websocket.receive_json()["type"] == "realtime.ready"
            websocket.send_json({"type": "auth.renew", "access_token": other_login["access_token"]})
            try:
                websocket.receive_json()
                raise AssertionError("identity-switch renewal remained connected")
            except WebSocketDisconnect as exc:
                assert exc.code == 4403

    def test_realtime_closes_after_device_revocation(self) -> None:
        self._enroll_device()
        login = self._login("device-123")
        with self.client.websocket_connect(
            "/api/web-app/realtime",
            headers={
                "Host": "0123456789abcdef.hexe-ai.com",
                "Authorization": f"Bearer {login['access_token']}",
            },
        ) as websocket:
            assert websocket.receive_json()["type"] == "realtime.ready"
            self.devices._conn.execute(
                "UPDATE web_app_devices SET revoked_at = ? WHERE device_id = ?",
                ("2026-09-30T01:00:00+00:00", "device-123"),
            )
            try:
                websocket.receive_json()
                raise AssertionError("revoked websocket remained connected")
            except WebSocketDisconnect as exc:
                assert exc.code == 4403
