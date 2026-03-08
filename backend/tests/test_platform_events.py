import asyncio
import tempfile
import time
import unittest
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.addons.models import AddonMeta, BackendAddon
from app.addons.registry import AddonRegistry
from app.system.auth import ServiceTokenKeyStore, sign_hs256
from app.system.events import PlatformEventService, build_events_router
from app.system.services import ServiceCatalogStore, build_service_resolution_router


class _FakeSettingsStore:
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    async def get(self, key: str):
        return self._data.get(key)

    async def set(self, key: str, value):
        self._data[key] = value
        return value


class TestPlatformEvents(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.settings = _FakeSettingsStore()
        self.key_store = ServiceTokenKeyStore(self.settings)
        self.catalog_store = ServiceCatalogStore(str(Path(self.tmpdir.name) / "service_catalogs.json"))
        self.events = PlatformEventService(max_events=50)
        self.registry = AddonRegistry(
            addons={
                "vision-addon": BackendAddon(
                    meta=AddonMeta(
                        id="vision-addon",
                        name="Vision Addon",
                        version="1.0.0",
                        capabilities=[],
                    ),
                    router=APIRouter(),
                )
            },
            errors={},
            enabled={},
            registered={},
        )
        app = FastAPI()
        app.include_router(build_events_router(self.events), prefix="/api/system")
        app.include_router(
            build_service_resolution_router(self.registry, self.catalog_store, self.key_store, self.events),
            prefix="/api/services",
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _token(self, *, sub: str, scopes: list[str]) -> str:
        key = asyncio.run(self.key_store.active_key())
        now = int(time.time())
        return sign_hs256(
            {"alg": "HS256", "typ": "JWT", "kid": key["kid"]},
            {
                "sub": sub,
                "aud": "synthia-core",
                "scp": scopes,
                "exp": now + 600,
                "iat": now,
                "jti": f"jti-{now}",
            },
            key["secret"],
        )

    def test_event_api_lists_recent_events(self) -> None:
        asyncio.run(self.events.emit(event_type="addon_installed", source="store.api", payload={"addon_id": "a1"}))
        resp = self.client.get("/api/system/events", params={"limit": 10})
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["items"][0]["event_type"], "addon_installed")
        self.assertEqual(data["items"][0]["source"], "store.api")

    def test_service_register_emits_service_registered_event(self) -> None:
        register = self.client.post(
            "/api/services/register",
            headers={"Authorization": f"Bearer {self._token(sub='vision-addon', scopes=['services.register'])}"},
            json={
                "service_type": "ai-service",
                "addon_id": "vision-addon",
                "endpoint": "http://127.0.0.1:9000",
                "health": "healthy",
                "capabilities": ["ai.embed"],
            },
        )
        self.assertEqual(register.status_code, 200, register.text)

        events = self.client.get("/api/system/events", params={"event_type": "service_registered"})
        self.assertEqual(events.status_code, 200, events.text)
        items = events.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["event_type"], "service_registered")
        self.assertEqual(items[0]["payload"]["addon_id"], "vision-addon")


if __name__ == "__main__":
    unittest.main()
