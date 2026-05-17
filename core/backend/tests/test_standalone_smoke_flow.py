from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.addons.proxy import build_proxy_router
from app.store.audit import StoreAuditLogStore
from app.store.router import build_store_router
from app.store.sources import StoreSource


class _FakeMeta:
    def __init__(self, version: str = "1.0.0") -> None:
        self.version = version


class _FakeAddon:
    def __init__(self, version: str = "1.0.0") -> None:
        self.meta = _FakeMeta(version=version)
        self.health_status = "registered"


class _FakeRegistry:
    def __init__(self) -> None:
        self.addons = {"hello_world": _FakeAddon("1.0.0")}
        self.enabled: dict[str, bool] = {}

    def is_enabled(self, addon_id: str) -> bool:
        return self.enabled.get(addon_id, True)

    def set_enabled(self, addon_id: str, enabled: bool) -> None:
        self.enabled[addon_id] = enabled


class _FakeSourcesStore:
    async def list_sources(self):
        return [
            StoreSource(
                id="official",
                type="github_raw",
                base_url="https://raw.githubusercontent.test/catalog",
                enabled=True,
                refresh_seconds=300,
            )
        ]


class _FakeCatalogClient:
    def __init__(self, artifact_bytes: bytes) -> None:
        digest = hashlib.sha256(artifact_bytes).hexdigest()
        self._artifact_bytes = artifact_bytes
        self._index_payload = {
            "addons": [
                {
                    "id": "hello_world",
                    "name": "hello_world",
                    "publisher_id": "pub-1",
                    "permissions": ["filesystem.read"],
                    "releases": [
                        {
                            "version": "1.0.0",
                            "sha256": digest,
                            "checksum": digest,
                            "publisher_key_id": "key-1",
                            "package_profile": "standalone_service",
                            "artifact_url": "https://example.test/hello_world-1.0.0.tgz",
                            "compatibility": {
                                "core_min_version": "0.1.0",
                                "core_max_version": None,
                                "dependencies": [],
                                "conflicts": [],
                            },
                        }
                    ],
                }
            ]
        }
        self._publishers_payload = {
            "publishers": [
                {
                    "id": "pub-1",
                    "enabled": True,
                    "keys": [
                        {
                            "id": "key-1",
                            "enabled": True,
                            "signature_type": "rsa-sha256",
                            "public_key_pem": "unused",
                        }
                    ],
                }
            ]
        }

    def select_source(self, sources, source_id):
        for src in sources:
            if src.id == (source_id or "official"):
                return src
        return None

    def load_cached_documents(self, source_id: str):
        if source_id != "official":
            return None, None
        return self._index_payload, self._publishers_payload

    def download_artifact(self, url: str) -> bytes:
        return self._artifact_bytes

    def refresh_source(self, source):
        return {"ok": True, "source_id": source.id, "catalog_status": {"status": "ok"}}

    def load_source_metadata(self, source_id: str) -> dict:
        return {"source_id": source_id, "resolved_base_url": "https://raw.githubusercontent.test/catalog"}


class _FakeProxy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def forward(self, request: Request, addon_id: str, path: str = "") -> JSONResponse:
        self.calls.append((request.method, addon_id, path))
        return JSONResponse({"ok": True, "addon_id": addon_id, "path": path})


class TestStandaloneSmokeFlow(unittest.TestCase):
    def setUp(self) -> None:
        self.old_token = os.environ.get("SYNTHIA_ADMIN_TOKEN")
        os.environ["SYNTHIA_ADMIN_TOKEN"] = "test-token"
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()
        if self.old_token is None:
            os.environ.pop("SYNTHIA_ADMIN_TOKEN", None)
        else:
            os.environ["SYNTHIA_ADMIN_TOKEN"] = self.old_token

    def test_standalone_install_runtime_health_and_ui_proxy_smoke(self) -> None:
        standalone_root = Path(self.tmp.name) / "SynthiaAddons"
        artifact_bytes = b"standalone-artifact"
        registry = _FakeRegistry()
        audit = StoreAuditLogStore(str(Path(self.tmp.name) / "store_audit.db"))
        catalog = _FakeCatalogClient(artifact_bytes)
        proxy = _FakeProxy()

        app = FastAPI()
        app.include_router(
            build_store_router(registry, audit, sources_store=_FakeSourcesStore(), catalog_client=catalog),
            prefix="/api/store",
        )
        app.include_router(build_proxy_router(proxy))
        client = TestClient(app)

        with patch.dict(os.environ, {"SYNTHIA_ADDONS_DIR": str(standalone_root)}, clear=False):
            install = client.post(
                "/api/store/install",
                headers={"X-Admin-Token": "test-token"},
                json={
                    "source_id": "official",
                    "addon_id": "hello_world",
                    "install_mode": "standalone_service",
                    "desired_state": "running",
                    "runtime_overrides": {
                        "project_name": "synthia-addon-hello",
                        "network": "synthia_net",
                        "ports": [{"host": 18081, "container": 18081, "proto": "tcp"}],
                        "bind_localhost": False,
                    },
                },
            )

            self.assertEqual(install.status_code, 200, install.text)
            payload = install.json()
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mode"], "standalone_service")
            self.assertEqual(payload["runtime_state"], "unknown")

            runtime_path = standalone_root / "services" / "hello_world" / "runtime.json"
            runtime_path.parent.mkdir(parents=True, exist_ok=True)
            runtime_path.write_text(
                json.dumps(
                    {
                        "ssap_version": "1.0",
                        "addon_id": "hello_world",
                        "active_version": "1.0.0",
                        "state": "running",
                        "health": {"status": "ok"},
                    }
                ),
                encoding="utf-8",
            )

            status = client.get("/api/store/status/hello_world")
            self.assertEqual(status.status_code, 200, status.text)
            status_payload = status.json()
            self.assertEqual(status_payload["runtime_state"], "running")
            self.assertEqual(status_payload["standalone_runtime"]["health"]["status"], "ok")

            health = client.get("/api/addons/hello_world/api/addon/health")
            self.assertEqual(health.status_code, 200, health.text)
            ui = client.get("/addons/hello_world/ui")
            self.assertEqual(ui.status_code, 200, ui.text)

        self.assertEqual(
            proxy.calls,
            [
                ("GET", "hello_world", "api/addon/health"),
                ("GET", "hello_world", "ui"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
