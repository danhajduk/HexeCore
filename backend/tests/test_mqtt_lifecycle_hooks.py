import os
import unittest
from unittest.mock import patch

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.addons.models import AddonMeta, BackendAddon, RegisteredAddon
from app.addons.registry import AddonRegistry
from app.api.admin_registry import build_admin_registry_router
from app.api.system import build_system_router


class _FakeMqttApprovalService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def reconcile(self, addon_id: str):
        self.calls.append(("reconcile", addon_id))
        return {"ok": True}

    async def revoke_or_mark(self, addon_id: str, reason: str):
        self.calls.append(("revoke", f"{addon_id}:{reason}"))
        return {"ok": True}


class TestMqttLifecycleHooks(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(os.environ, {"SYNTHIA_ADMIN_TOKEN": "test-token"}, clear=False)
        self.env_patch.start()
        self.service = _FakeMqttApprovalService()
        self.registry = AddonRegistry(
            addons={
                "vision": BackendAddon(
                    meta=AddonMeta(id="vision", name="Vision", version="1.0.0"),
                    router=APIRouter(),
                )
            },
            errors={},
            enabled={"vision": True},
            registered={
                "vision": RegisteredAddon(
                    id="vision",
                    name="Vision",
                    version="1.0.0",
                    base_url="http://127.0.0.1:9010",
                )
            },
        )
        app = FastAPI()
        app.include_router(build_system_router(self.registry, mqtt_approval_service=self.service), prefix="/api")
        app.include_router(build_admin_registry_router(self.registry, mqtt_approval_service=self.service), prefix="/api")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()

    def test_disable_and_enable_hooks(self) -> None:
        disable = self.client.post("/api/addons/vision/enable", json={"enabled": False})
        self.assertEqual(disable.status_code, 200, disable.text)
        enable = self.client.post("/api/addons/vision/enable", json={"enabled": True})
        self.assertEqual(enable.status_code, 200, enable.text)
        self.assertIn(("revoke", "vision:addon_disabled"), self.service.calls)
        self.assertIn(("reconcile", "vision"), self.service.calls)

    def test_admin_registry_delete_triggers_revocation_hook(self) -> None:
        deleted = self.client.delete("/api/admin/addons/registry/vision", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertIn(("revoke", "vision:addon_untrusted_or_removed"), self.service.calls)


if __name__ == "__main__":
    unittest.main()
