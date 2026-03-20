import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    FASTAPI_STACK_AVAILABLE = True
except Exception:  # pragma: no cover
    FastAPI = None
    TestClient = None
    FASTAPI_STACK_AVAILABLE = False

from app.system.platform_identity import (
    DEFAULT_PLATFORM_DOMAIN,
    DEFAULT_PLATFORM_NAME,
    DEFAULT_PLATFORM_SHORT,
    default_platform_identity,
    load_platform_identity,
    platform_identity_from_values,
)
from app.system.settings.router import build_settings_router
from app.system.settings.store import SettingsStore


class TestPlatformIdentity(unittest.TestCase):
    def test_default_platform_identity_uses_phase_zero_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            identity = default_platform_identity()
        self.assertEqual(identity.platform_name, DEFAULT_PLATFORM_NAME)
        self.assertEqual(identity.platform_short, DEFAULT_PLATFORM_SHORT)
        self.assertEqual(identity.platform_domain, DEFAULT_PLATFORM_DOMAIN)
        self.assertEqual(identity.core_name, f"{DEFAULT_PLATFORM_SHORT} Core")

    def test_platform_identity_uses_env_overrides(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PLATFORM_NAME": "Acme AI",
                "PLATFORM_SHORT": "Acme",
                "PLATFORM_DOMAIN": "acme.example",
                "PLATFORM_CORE_NAME": "Acme Control",
            },
            clear=True,
        ):
            identity = default_platform_identity()
        self.assertEqual(identity.platform_name, "Acme AI")
        self.assertEqual(identity.platform_short, "Acme")
        self.assertEqual(identity.platform_domain, "acme.example")
        self.assertEqual(identity.core_name, "Acme Control")

    def test_platform_identity_prefers_settings_values(self) -> None:
        with patch.dict(os.environ, {"PLATFORM_NAME": "Env AI"}, clear=True):
            identity = platform_identity_from_values(
                {
                    "platform.name": "Hexe AI",
                    "platform.short": "Hexe",
                    "platform.domain": "hexe-ai.com",
                    "app.name": "Hexe Core",
                }
            )
        self.assertEqual(identity.platform_name, "Hexe AI")
        self.assertEqual(identity.platform_short, "Hexe")
        self.assertEqual(identity.platform_domain, "hexe-ai.com")
        self.assertEqual(identity.core_name, "Hexe Core")


@unittest.skipIf(not FASTAPI_STACK_AVAILABLE, "fastapi/testclient not available in this environment")
class TestPlatformIdentityApi(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = SettingsStore(str(Path(self.tmpdir.name) / "app_settings.db"))
        app = FastAPI()
        app.include_router(build_settings_router(self.store), prefix="/api/system")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_platform_endpoint_returns_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            res = self.client.get("/api/system/platform")
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["platform_name"], DEFAULT_PLATFORM_NAME)
        self.assertEqual(payload["platform_short"], DEFAULT_PLATFORM_SHORT)
        self.assertEqual(payload["platform_domain"], DEFAULT_PLATFORM_DOMAIN)
        self.assertEqual(payload["core_name"], f"{DEFAULT_PLATFORM_SHORT} Core")

    def test_platform_endpoint_returns_settings_overrides(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.store._set_sync("platform.name", "Hexe AI")
            self.store._set_sync("platform.short", "Hexe")
            self.store._set_sync("platform.domain", "hexe-ai.com")
            self.store._set_sync("app.name", "Hexe Core")
            res = self.client.get("/api/system/platform")
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertEqual(payload["platform_name"], "Hexe AI")
        self.assertEqual(payload["platform_short"], "Hexe")
        self.assertEqual(payload["platform_domain"], "hexe-ai.com")
        self.assertEqual(payload["core_name"], "Hexe Core")


class TestLoadPlatformIdentity(unittest.IsolatedAsyncioTestCase):
    async def test_async_loader_uses_settings_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SettingsStore(str(Path(tmpdir) / "app_settings.db"))
            await store.set("platform.name", "Hexe AI")
            await store.set("platform.short", "Hexe")
            await store.set("platform.domain", "hexe-ai.com")
            identity = await load_platform_identity(store)
        self.assertEqual(identity.platform_name, "Hexe AI")
        self.assertEqual(identity.platform_short, "Hexe")
        self.assertEqual(identity.platform_domain, "hexe-ai.com")
        self.assertEqual(identity.core_name, "Hexe Core")


if __name__ == "__main__":
    unittest.main()
