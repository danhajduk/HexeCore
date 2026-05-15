import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.system.supervisors import SupervisorFleetStore, build_supervisors_router


class TestSupervisorFleetApi(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(os.environ, {"SYNTHIA_ADMIN_TOKEN": "test-token"}, clear=False)
        self.env_patch.start()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = SupervisorFleetStore(path=Path(self.tmpdir.name) / "supervisors.json")
        app = FastAPI()
        app.include_router(build_supervisors_router(self.store), prefix="/api/system")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.tmpdir.cleanup()

    def test_supervisor_register_and_heartbeat_flow(self) -> None:
        headers = {"X-Admin-Token": "test-token"}
        registered = self.client.post(
            "/api/system/supervisors/register",
            headers=headers,
            json={
                "supervisor_id": "host-a",
                "supervisor_name": "Host A Supervisor",
                "host_id": "host-a",
                "hostname": "host-a.local",
                "api_base_url": "http://10.0.0.12:57665",
                "transport": "http",
                "capabilities": ["host_resources", "runtime_control"],
            },
        )
        self.assertEqual(registered.status_code, 200, registered.text)
        supervisor = registered.json()["supervisor"]
        self.assertEqual(supervisor["supervisor_id"], "host-a")
        self.assertEqual(supervisor["freshness_state"], "offline")

        heartbeat = self.client.post(
            "/api/system/supervisors/heartbeat",
            headers=headers,
            json={
                "supervisor_id": "host-a",
                "health_status": "healthy",
                "lifecycle_state": "running",
                "resources": {"cpu_percent_total": 12.5, "memory_percent": 40.0},
                "managed_node_count": 2,
                "registered_runtime_count": 3,
                "core_runtime_count": 0,
            },
        )
        self.assertEqual(heartbeat.status_code, 200, heartbeat.text)
        updated = heartbeat.json()["supervisor"]
        self.assertEqual(updated["health_status"], "healthy")
        self.assertEqual(updated["freshness_state"], "online")
        self.assertEqual(updated["managed_node_count"], 2)

        listed = self.client.get("/api/system/supervisors", headers=headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["items"][0]["supervisor_id"], "host-a")

    def test_supervisor_routes_require_admin(self) -> None:
        denied = self.client.get("/api/system/supervisors")
        self.assertEqual(denied.status_code, 401, denied.text)


if __name__ == "__main__":
    unittest.main()
