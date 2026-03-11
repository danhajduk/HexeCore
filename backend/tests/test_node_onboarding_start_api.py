import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.system import build_system_router
    FASTAPI_STACK_AVAILABLE = True
except Exception:  # pragma: no cover - local env may not include FastAPI deps
    FastAPI = None
    TestClient = None
    build_system_router = None
    FASTAPI_STACK_AVAILABLE = False

from app.system.onboarding import NodeOnboardingSessionsStore


class _FakeRegistry:
    def has_addon(self, addon_id: str) -> bool:
        return False

    def is_platform_managed(self, addon_id: str) -> bool:
        return False

    def set_enabled(self, addon_id: str, enabled: bool) -> None:
        return None

    def is_enabled(self, addon_id: str) -> bool:
        return False

    @property
    def errors(self):
        return []


@unittest.skipIf(not FASTAPI_STACK_AVAILABLE, "fastapi/testclient not available in this environment")
class TestNodeOnboardingStartApi(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = NodeOnboardingSessionsStore(path=Path(self.tmpdir.name) / "node_onboarding_sessions.json")
        app = FastAPI()
        app.include_router(build_system_router(_FakeRegistry(), onboarding_sessions_store=self.store), prefix="/api")
        self.client = TestClient(app)
        self.env_patch = patch.dict(
            os.environ,
            {
                "SYNTHIA_AI_NODE_ONBOARDING_ENABLED": "true",
                "SYNTHIA_AI_NODE_ONBOARDING_PROTOCOLS": "1.0",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.tmpdir.cleanup()

    def _payload(self) -> dict[str, str]:
        return {
            "node_name": "office-node",
            "node_type": "ai-node",
            "node_software_version": "0.1.0",
            "protocol_version": "1.0",
            "hostname": "office-node-host",
            "node_nonce": "nonce-abc",
        }

    def test_start_session_success(self) -> None:
        resp = self.client.post("/api/system/nodes/onboarding/sessions", json=self._payload())
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        session = body["session"]
        self.assertEqual(session["onboarding_status"], "pending_approval")
        self.assertIn("session_id", session)
        self.assertIn("approval_url", session)
        self.assertIn("expires_at", session)
        self.assertEqual(session["finalize"]["method"], "GET")
        self.assertIn("/api/system/nodes/onboarding/sessions/", session["finalize"]["path"])

    def test_duplicate_active_session(self) -> None:
        first = self.client.post("/api/system/nodes/onboarding/sessions", json=self._payload())
        self.assertEqual(first.status_code, 200, first.text)

        second = self.client.post("/api/system/nodes/onboarding/sessions", json=self._payload())
        self.assertEqual(second.status_code, 409, second.text)
        self.assertEqual(second.json()["detail"]["error"], "duplicate_active_session")

    def test_node_type_unsupported(self) -> None:
        payload = self._payload()
        payload["node_type"] = "not-ai-node"
        resp = self.client.post("/api/system/nodes/onboarding/sessions", json=payload)
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["detail"]["error"], "node_type_unsupported")

    def test_registration_disabled(self) -> None:
        with patch.dict(os.environ, {"SYNTHIA_AI_NODE_ONBOARDING_ENABLED": "false"}, clear=False):
            resp = self.client.post("/api/system/nodes/onboarding/sessions", json=self._payload())
        self.assertEqual(resp.status_code, 503, resp.text)
        self.assertEqual(resp.json()["detail"]["error"], "registration_disabled")


if __name__ == "__main__":
    unittest.main()
