from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.store.router import StoreAuditLogStore, build_store_router


class _FakeRegistry:
    def __init__(self) -> None:
        self.addons = {}
        self.enabled = {}

    def is_enabled(self, addon_id: str) -> bool:
        return self.enabled.get(addon_id, True)

    def set_enabled(self, addon_id: str, enabled: bool) -> None:
        self.enabled[addon_id] = enabled


class TestStoreAuditEndpoint(unittest.TestCase):
    def test_admin_audit_endpoint_filters(self) -> None:
        old_token = os.environ.get("SYNTHIA_ADMIN_TOKEN")
        os.environ["SYNTHIA_ADMIN_TOKEN"] = "test-token"
        try:
            with tempfile.TemporaryDirectory() as td:
                db_path = str(Path(td) / "store_audit.db")
                audit = StoreAuditLogStore(db_path)
                app = FastAPI()
                app.include_router(build_store_router(_FakeRegistry(), audit), prefix="/api/store")
                client = TestClient(app)

                import asyncio
                asyncio.run(
                    audit.record(
                        action="install",
                        addon_id="addon_a",
                        version="1.0.0",
                        status="success",
                        message="install_completed",
                        actor="admin_token",
                    )
                )
                asyncio.run(
                    audit.record(
                        action="update",
                        addon_id="addon_b",
                        version="1.1.0",
                        status="failed",
                        message="signature_invalid",
                        actor="admin_token",
                    )
                )

                res = client.get(
                    "/api/store/admin/audit?status=failed",
                    headers={"X-Admin-Token": "test-token"},
                )
                self.assertEqual(res.status_code, 200, res.text)
                payload = res.json()
                self.assertEqual(payload["total"], 1)
                self.assertEqual(payload["items"][0]["addon_id"], "addon_b")
                self.assertEqual(payload["items"][0]["status"], "failed")

                all_rows = client.get(
                    "/api/store/admin/audit",
                    headers={"X-Admin-Token": "test-token"},
                )
                self.assertEqual(all_rows.status_code, 200, all_rows.text)
                rows_payload = all_rows.json()
                self.assertEqual(rows_payload["total"], 2)
                newer_ts = rows_payload["items"][0]["timestamp"]
                older_ts = rows_payload["items"][1]["timestamp"]

                older_only = client.get(
                    "/api/store/admin/audit",
                    params={"to_ts": older_ts},
                    headers={"X-Admin-Token": "test-token"},
                )
                self.assertEqual(older_only.status_code, 200, older_only.text)
                older_payload = older_only.json()
                self.assertEqual(older_payload["total"], 1)
                self.assertEqual(older_payload["items"][0]["timestamp"], older_ts)

                newer_only = client.get(
                    "/api/store/admin/audit",
                    params={"from_ts": newer_ts},
                    headers={"X-Admin-Token": "test-token"},
                )
                self.assertEqual(newer_only.status_code, 200, newer_only.text)
                newer_payload = newer_only.json()
                self.assertEqual(newer_payload["total"], 1)
                self.assertEqual(newer_payload["items"][0]["timestamp"], newer_ts)
        finally:
            if old_token is None:
                os.environ.pop("SYNTHIA_ADMIN_TOKEN", None)
            else:
                os.environ["SYNTHIA_ADMIN_TOKEN"] = old_token


if __name__ == "__main__":
    unittest.main()
