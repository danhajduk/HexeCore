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
from app.system.services import ServiceCatalogStore, build_service_resolution_router


class _FakeSettingsStore:
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    async def get(self, key: str):
        return self._data.get(key)

    async def set(self, key: str, value):
        self._data[key] = value
        return value


class TestServicesApi(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.settings = _FakeSettingsStore()
        self.key_store = ServiceTokenKeyStore(self.settings)
        self.catalog_store = ServiceCatalogStore(str(Path(self.tmpdir.name) / "service_catalogs.json"))
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
        app.include_router(
            build_service_resolution_router(self.registry, self.catalog_store, self.key_store),
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

    def test_register_requires_service_token_scope(self) -> None:
        resp = self.client.post(
            "/api/services/register",
            json={
                "service_type": "ai-service",
                "addon_id": "vision-addon",
                "endpoint": "http://127.0.0.1:9000",
                "health": "healthy",
                "capabilities": ["ai.embed"],
            },
        )
        self.assertEqual(resp.status_code, 401, resp.text)
        self.assertEqual(resp.json()["detail"], "service_token_missing")

        no_scope = self.client.post(
            "/api/services/register",
            headers={"Authorization": f"Bearer {self._token(sub='vision-addon', scopes=['telemetry.write'])}"},
            json={
                "service_type": "ai-service",
                "addon_id": "vision-addon",
                "endpoint": "http://127.0.0.1:9000",
                "health": "healthy",
                "capabilities": ["ai.embed"],
            },
        )
        self.assertEqual(no_scope.status_code, 401, no_scope.text)
        self.assertEqual(no_scope.json()["detail"], "claim_scope_missing")

    def test_register_enforces_subject_addon_binding(self) -> None:
        resp = self.client.post(
            "/api/services/register",
            headers={"Authorization": f"Bearer {self._token(sub='other-addon', scopes=['services.register'])}"},
            json={
                "service_type": "ai-service",
                "addon_id": "vision-addon",
                "endpoint": "http://127.0.0.1:9000",
                "health": "healthy",
                "capabilities": ["ai.embed"],
            },
        )
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertEqual(resp.json()["detail"], "service_registration_subject_mismatch")

    def test_register_persists_service_and_resolve_uses_catalog(self) -> None:
        register = self.client.post(
            "/api/services/register",
            headers={"Authorization": f"Bearer {self._token(sub='vision-addon', scopes=['services.register'])}"},
            json={
                "service_type": "ai-service",
                "addon_id": "vision-addon",
                "endpoint": "http://127.0.0.1:9000",
                "health": "healthy",
                "capabilities": ["ai.embed", "ai.classify"],
            },
        )
        self.assertEqual(register.status_code, 200, register.text)
        payload = register.json()["service"]
        self.assertEqual(payload["service_type"], "ai-service")
        self.assertEqual(payload["addon_id"], "vision-addon")
        self.assertEqual(payload["auth_mode"], "service_token")
        self.assertTrue(payload["addon_registry"]["loaded_local"])

        resolve = self.client.get("/api/services/resolve", params={"capability": "ai.embed"})
        self.assertEqual(resolve.status_code, 200, resolve.text)
        resolved = resolve.json()
        self.assertEqual(resolved["source"], "catalog")
        self.assertEqual(resolved["provider"]["addon_id"], "vision-addon")
        self.assertEqual(resolved["provider"]["endpoint"], "http://127.0.0.1:9000")
        self.assertEqual(resolved["provider"]["health"], "healthy")


if __name__ == "__main__":
    unittest.main()
