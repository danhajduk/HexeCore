import os
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from app.addons.proxy import AddonProxy, build_proxy_router


class _FakeRegistry:
    def __init__(self) -> None:
        self.registered = {}
        self.addons = {"mqtt": object()}


class TestAddonsProxyLocalEmbedded(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(os.environ, {"SYNTHIA_ADMIN_TOKEN": "test-token"}, clear=False)
        self.env_patch.start()
        self.proxy = AddonProxy(_FakeRegistry())
        app = FastAPI()

        @app.get("/api/addons/mqtt", response_class=HTMLResponse)
        async def mqtt_ui_root():
            return "<html><body>mqtt local ui</body></html>"

        app.include_router(build_proxy_router(self.proxy))
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()

    def test_ui_proxy_uses_local_embedded_target(self) -> None:
        with patch.object(self.proxy._client, "request") as request_mock:
            res = self.client.get("/ui/addons/mqtt", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIn("mqtt local ui", res.text)
        request_mock.assert_not_called()

    def test_alias_proxy_uses_local_embedded_target(self) -> None:
        with patch.object(self.proxy._client, "request") as request_mock:
            res = self.client.get("/addons/proxy/mqtt", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIn("mqtt local ui", res.text)
        request_mock.assert_not_called()

    def test_missing_addon_still_returns_not_found(self) -> None:
        res = self.client.get("/ui/addons/missing", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(res.status_code, 404, res.text)
        self.assertIn("Addon UI Unavailable", res.text)
        self.assertIn("registered_addon_not_found", res.text)


if __name__ == "__main__":
    unittest.main()
