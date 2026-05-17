import json
import os
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.system.auth import ServiceTokenKeyStore, build_auth_router, verify_hs256


class _FakeSettingsStore:
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    async def get(self, key: str):
        return self._data.get(key)

    async def set(self, key: str, value):
        self._data[key] = value
        return value


class TestAuthApi(unittest.TestCase):
    def setUp(self) -> None:
        principals = json.dumps(
            [
                {
                    "id": "vision-addon",
                    "secret": "vision-secret",
                    "subject": "vision-addon",
                    "allowed_audiences": ["ai-service"],
                    "allowed_scopes": ["ai.classify", "ai.embed"],
                    "max_ttl_s": 900,
                }
            ]
        )
        self.env_patch = patch.dict(
            os.environ,
            {
                "SYNTHIA_ADMIN_TOKEN": "test-token",
                "SYNTHIA_SERVICE_PRINCIPALS_JSON": principals,
            },
            clear=False,
        )
        self.env_patch.start()
        self.settings = _FakeSettingsStore()
        self.key_store = ServiceTokenKeyStore(self.settings)
        app = FastAPI()
        app.include_router(build_auth_router(self.key_store), prefix="/api/auth")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()

    def test_issue_token_with_admin_token(self) -> None:
        exp = int(time.time()) + 300
        resp = self.client.post(
            "/api/auth/service-token",
            headers={"X-Admin-Token": "test-token"},
            json={"sub": "vision-addon", "aud": "ai-service", "scp": ["ai.classify"], "exp": exp},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["issued_by"]["mode"], "admin")

    def test_issue_token_with_service_principal(self) -> None:
        exp = int(time.time()) + 600
        resp = self.client.post(
            "/api/auth/service-token",
            headers={
                "X-Service-Principal-Id": "vision-addon",
                "X-Service-Principal-Secret": "vision-secret",
            },
            json={"sub": "vision-addon", "aud": "ai-service", "scp": ["ai.embed"], "exp": exp},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["issued_by"]["mode"], "service_principal")
        self.assertEqual(payload["issued_by"]["id"], "vision-addon")

        token = payload["token"]
        keyring = self.settings._data["auth.service_token.keys"]  # type: ignore[index]
        keys = keyring if isinstance(keyring, list) else []
        _, claims = verify_hs256(token, keys)
        self.assertEqual(claims["sub"], "vision-addon")
        self.assertEqual(claims["aud"], "ai-service")
        self.assertIn("ai.embed", claims["scp"])

    def test_service_principal_enforces_subject_scope_audience_and_ttl(self) -> None:
        exp = int(time.time()) + 600
        bad_subject = self.client.post(
            "/api/auth/service-token",
            headers={
                "X-Service-Principal-Id": "vision-addon",
                "X-Service-Principal-Secret": "vision-secret",
            },
            json={"sub": "other-addon", "aud": "ai-service", "scp": ["ai.embed"], "exp": exp},
        )
        self.assertEqual(bad_subject.status_code, 403, bad_subject.text)
        self.assertEqual(bad_subject.json()["detail"], "service_principal_subject_mismatch")

        bad_scope = self.client.post(
            "/api/auth/service-token",
            headers={
                "X-Service-Principal-Id": "vision-addon",
                "X-Service-Principal-Secret": "vision-secret",
            },
            json={"sub": "vision-addon", "aud": "ai-service", "scp": ["gmail.send"], "exp": exp},
        )
        self.assertEqual(bad_scope.status_code, 403, bad_scope.text)
        self.assertEqual(bad_scope.json()["detail"], "service_principal_scope_forbidden")

        bad_audience = self.client.post(
            "/api/auth/service-token",
            headers={
                "X-Service-Principal-Id": "vision-addon",
                "X-Service-Principal-Secret": "vision-secret",
            },
            json={"sub": "vision-addon", "aud": "storage-service", "scp": ["ai.embed"], "exp": exp},
        )
        self.assertEqual(bad_audience.status_code, 403, bad_audience.text)
        self.assertEqual(bad_audience.json()["detail"], "service_principal_audience_forbidden")

        ttl_too_long = self.client.post(
            "/api/auth/service-token",
            headers={
                "X-Service-Principal-Id": "vision-addon",
                "X-Service-Principal-Secret": "vision-secret",
            },
            json={"sub": "vision-addon", "aud": "ai-service", "scp": ["ai.embed"], "exp": int(time.time()) + 3600},
        )
        self.assertEqual(ttl_too_long.status_code, 400, ttl_too_long.text)
        self.assertEqual(ttl_too_long.json()["detail"], "service_principal_ttl_exceeds_max")


if __name__ == "__main__":
    unittest.main()
