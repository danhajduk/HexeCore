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

from app.edge import EdgeGatewayService, EdgeGatewayStore, build_edge_router
from app.system.onboarding import NodeRegistrationsStore
from app.system.settings.router import build_settings_router
from app.system.settings.store import SettingsStore
from app.supervisor.service import SupervisorDomainService


@unittest.skipIf(not FASTAPI_STACK_AVAILABLE, "fastapi/testclient not available in this environment")
class TestEdgeGatewayApi(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self.settings = SettingsStore(str(base / "app_settings.db"))
        self.edge_store = EdgeGatewayStore(str(base / "edge_gateway.json"))
        self.registrations = NodeRegistrationsStore(path=base / "node_registrations.json")
        self.supervisor = SupervisorDomainService()
        self.service = EdgeGatewayService(
            self.edge_store,
            settings_store=self.settings,
            node_registrations_store=self.registrations,
            supervisor_service=self.supervisor,
        )
        app = FastAPI()
        app.include_router(build_settings_router(self.settings), prefix="/api/system")
        app.include_router(build_edge_router(self.service), prefix="/api")
        self.client = TestClient(app)
        self.env = patch.dict(
            os.environ,
            {
                "SYNTHIA_ADMIN_TOKEN": "test-token",
                "SYNTHIA_EDGE_RUNTIME_DIR": str(base / "edge-runtime"),
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmpdir.cleanup()

    def test_public_identity_and_platform_endpoint_share_core_id(self) -> None:
        platform_payload = self.client.get("/api/system/platform").json()
        edge_payload = self.client.get("/api/edge/public-identity").json()
        self.assertEqual(platform_payload["core_id"], edge_payload["core_id"])
        self.assertEqual(platform_payload["public_ui_hostname"], edge_payload["public_ui_hostname"])
        self.assertEqual(platform_payload["public_api_hostname"], edge_payload["public_api_hostname"])

    def test_create_publication_and_reconcile(self) -> None:
        identity = self.client.get("/api/edge/public-identity").json()
        created = self.client.post(
            "/api/edge/publications",
            headers={"X-Admin-Token": "test-token"},
            json={
                "hostname": f"service.{identity['core_id']}.hexe-ai.com",
                "path_prefix": "/mail",
                "enabled": True,
                "source": "operator_defined",
                "target": {
                    "target_type": "local_service",
                    "target_id": "mail-ui",
                    "upstream_base_url": "http://127.0.0.1:8081",
                    "allowed_path_prefixes": ["/mail"],
                },
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        listed = self.client.get("/api/edge/publications")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()["items"]), 3)

        settings_res = self.client.put(
            "/api/edge/cloudflare/settings",
            headers={"X-Admin-Token": "test-token"},
            json={
                "enabled": True,
                "account_id": "acct-1",
                "zone_id": "zone-1",
                "tunnel_id": "tunnel-1",
                "tunnel_name": "core-edge",
                "credentials_reference": "/tmp/cloudflare.json",
                "managed_domain_base": "hexe-ai.com",
                "hostname_publication_mode": "core_id_managed",
            },
        )
        self.assertEqual(settings_res.status_code, 200, settings_res.text)

        dry_run = self.client.post("/api/edge/cloudflare/test", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(dry_run.status_code, 200, dry_run.text)
        self.assertTrue(dry_run.json()["ok"])

        reconciled = self.client.post("/api/edge/reconcile", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(reconciled.status_code, 200, reconciled.text)
        status = self.client.get("/api/edge/status")
        self.assertEqual(status.status_code, 200, status.text)
        payload = status.json()
        self.assertTrue(payload["tunnel"]["configured"])
        self.assertIn("last_reconcile_at", payload["reconcile_state"])
