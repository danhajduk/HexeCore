import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.addons.install_sessions import InstallSessionsStore
from app.api.addons_install import build_addons_install_router


class _FakeRegistry:
    def __init__(self) -> None:
        self.registered = {"mqtt": {"id": "mqtt"}}

    async def configure_registered(self, addon_id: str, config: dict):
        if addon_id not in self.registered:
            raise RuntimeError("addon_not_registered")
        return {"applied": True, "config": config}

    async def verify_registered(self, addon_id: str):
        if addon_id not in self.registered:
            raise RuntimeError("addon_not_registered")
        return {"status": "ok"}


class TestAddonsInstallApi(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(
            os.environ,
            {
                "SYNTHIA_ADMIN_TOKEN": "test-token",
            },
            clear=False,
        )
        self.env_patch.start()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.sessions = InstallSessionsStore(path=Path(self.tmpdir.name) / "install_sessions.json")
        self.registry = _FakeRegistry()
        app = FastAPI()
        app.include_router(build_addons_install_router(self.registry, self.sessions), prefix="/api")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.tmpdir.cleanup()

    def test_install_flow(self) -> None:
        start = self.client.post(
            "/api/addons/install/start",
            headers={"X-Admin-Token": "test-token"},
            json={"addon_id": "mqtt"},
        )
        self.assertEqual(start.status_code, 200, start.text)
        session = start.json()["session"]
        sid = session["session_id"]
        self.assertEqual(session["state"], "pending_permissions")

        approve = self.client.post(
            f"/api/addons/install/{sid}/permissions/approve",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(approve.status_code, 200, approve.text)
        self.assertEqual(approve.json()["session"]["state"], "pending_deployment")

        deploy = self.client.post(
            f"/api/addons/install/{sid}/deployment/select",
            headers={"X-Admin-Token": "test-token"},
            json={"mode": "external"},
        )
        self.assertEqual(deploy.status_code, 200, deploy.text)
        self.assertEqual(deploy.json()["session"]["user_inputs"]["deployment_mode"], "external")

        self.sessions.mark_discovered("mqtt")
        got = self.client.get(f"/api/addons/install/{sid}")
        self.assertEqual(got.status_code, 200, got.text)
        self.assertEqual(got.json()["session"]["state"], "discovered")

        cfg = self.client.post(
            f"/api/addons/install/{sid}/configure",
            headers={"X-Admin-Token": "test-token"},
            json={"config": {"broker_host": "10.0.0.100"}},
        )
        self.assertEqual(cfg.status_code, 200, cfg.text)
        self.assertEqual(cfg.json()["session"]["state"], "configured")

        verify = self.client.post(
            f"/api/addons/install/{sid}/verify",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(verify.status_code, 200, verify.text)
        self.assertEqual(verify.json()["session"]["state"], "verified")

    def test_requires_admin_token(self) -> None:
        denied = self.client.post("/api/addons/install/start", json={"addon_id": "mqtt"})
        self.assertEqual(denied.status_code, 401, denied.text)


if __name__ == "__main__":
    unittest.main()
