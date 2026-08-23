import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.system.supervisors import SupervisorEnrollmentTokenStore, SupervisorFleetStore, build_supervisors_router


class _FakeSupervisorClient:
    def request_json(self, method: str, path: str, **_kwargs):  # noqa: ANN001
        self.requests.append((method, path))
        payloads = {
            "/api/supervisor/health": {
                "status": "ok",
                "host": {"host_id": "core-host", "hostname": "core-host"},
                "resources": {"cpu_percent_total": 10.0, "gpu_count": 0},
            },
            "/api/supervisor/runtime": {
                "host": {"host_id": "core-host", "hostname": "core-host"},
                "managed_nodes": [{"node_id": "local-node"}],
            },
            "/api/supervisor/info": {
                "supervisor_id": "local-core-supervisor",
                "host": {"host_id": "core-host", "hostname": "core-host"},
            },
            "/api/supervisor/runtimes": {"items": [{"node_id": "local-node", "node_name": "Local Node"}]},
            "/api/supervisor/core/runtimes": {"items": [{"runtime_id": "core-api", "runtime_name": "Core API"}]},
            "/api/supervisor/resources/history": {"scope": "host", "samples": [{"metrics": {"memory_percent": 41.0}}]},
            "/api/supervisor/runtimes/local-node/resources/history": {
                "scope": "runtime",
                "resource_id": "local-node",
                "samples": [],
            },
            "/api/supervisor/core/runtimes/core-api/resources/history": {
                "scope": "core_runtime",
                "resource_id": "core-api",
                "samples": [{"metrics": {"rps": 0.57}}],
            },
        }
        return payloads.get(path)

    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []


class TestSupervisorFleetApi(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(os.environ, {"HEXE_ADMIN_TOKEN": "test-token"}, clear=False)
        self.env_patch.start()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = SupervisorFleetStore(path=Path(self.tmpdir.name) / "supervisors.json")
        self.enrollment_store = SupervisorEnrollmentTokenStore(path=Path(self.tmpdir.name) / "supervisor_enrollment_tokens.json")
        app = FastAPI()
        app.include_router(build_supervisors_router(self.store, self.enrollment_store), prefix="/api/system")
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
                "registered_runtimes": [
                    {
                        "node_id": "node-ai",
                        "node_name": "AI Node",
                        "node_type": "ai-node",
                        "health_status": "healthy",
                    }
                ],
                "core_runtimes": [
                    {
                        "runtime_id": "addon:mqtt",
                        "runtime_name": "Hexe MQTT",
                        "runtime_kind": "addon",
                        "health_status": "healthy",
                    }
                ],
            },
        )
        self.assertEqual(heartbeat.status_code, 200, heartbeat.text)
        updated = heartbeat.json()["supervisor"]
        self.assertEqual(updated["health_status"], "healthy")
        self.assertEqual(updated["freshness_state"], "online")
        self.assertEqual(updated["managed_node_count"], 2)
        self.assertEqual(updated["registered_runtimes"][0]["node_id"], "node-ai")
        self.assertEqual(updated["core_runtimes"][0]["runtime_id"], "addon:mqtt")

        listed = self.client.get("/api/system/supervisors", headers=headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["items"][0]["supervisor_id"], "host-a")
        self.assertEqual(listed.json()["items"][0]["registered_runtimes"][0]["node_name"], "AI Node")

    def test_supervisor_routes_require_admin(self) -> None:
        denied = self.client.get("/api/system/supervisors")
        self.assertEqual(denied.status_code, 401, denied.text)

    def test_supervisor_enrollment_token_exchanges_for_reporting_token(self) -> None:
        headers = {"X-Admin-Token": "test-token"}
        created = self.client.post(
            "/api/system/supervisors/enrollment-tokens",
            headers=headers,
            json={"supervisor_id": "host-b", "supervisor_name": "Host B Supervisor", "ttl_seconds": 300},
        )
        self.assertEqual(created.status_code, 200, created.text)
        enrollment_token = created.json()["enrollment_token"]
        self.assertTrue(enrollment_token.startswith("hexe_sup_enroll_"))
        self.assertNotIn(enrollment_token, (Path(self.tmpdir.name) / "supervisor_enrollment_tokens.json").read_text())

        enrolled = self.client.post(
            "/api/system/supervisors/enroll",
            json={
                "enrollment_token": enrollment_token,
                "supervisor_id": "host-b",
                "supervisor_name": "Host B Supervisor",
                "host_id": "host-b",
                "hostname": "host-b.local",
                "capabilities": ["host_resources"],
            },
        )
        self.assertEqual(enrolled.status_code, 200, enrolled.text)
        reporting_token = enrolled.json()["reporting_token"]
        self.assertTrue(reporting_token.startswith("hexe_sup_report_"))
        self.assertNotIn("reporting_token_hash", enrolled.json()["supervisor"])

        heartbeat = self.client.post(
            "/api/system/supervisors/heartbeat",
            headers={"X-Supervisor-Token": reporting_token},
            json={
                "supervisor_id": "host-b",
                "health_status": "healthy",
                "lifecycle_state": "running",
            },
        )
        self.assertEqual(heartbeat.status_code, 200, heartbeat.text)
        self.assertEqual(heartbeat.json()["supervisor"]["freshness_state"], "online")

        reused = self.client.post(
            "/api/system/supervisors/enroll",
            json={"enrollment_token": enrollment_token, "supervisor_id": "host-b"},
        )
        self.assertEqual(reused.status_code, 409, reused.text)

    def test_supervisor_reporting_token_rejects_other_supervisors(self) -> None:
        headers = {"X-Admin-Token": "test-token"}
        created = self.client.post(
            "/api/system/supervisors/enrollment-tokens",
            headers=headers,
            json={"supervisor_id": "host-c"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        enrolled = self.client.post(
            "/api/system/supervisors/enroll",
            json={"enrollment_token": created.json()["enrollment_token"], "supervisor_id": "host-c"},
        )
        self.assertEqual(enrolled.status_code, 200, enrolled.text)

        denied = self.client.post(
            "/api/system/supervisors/heartbeat",
            headers={"X-Supervisor-Token": enrolled.json()["reporting_token"]},
            json={"supervisor_id": "host-d", "health_status": "healthy"},
        )
        self.assertEqual(denied.status_code, 401, denied.text)

    def test_list_syncs_local_core_attached_supervisor(self) -> None:
        app = FastAPI()
        supervisor_client = _FakeSupervisorClient()
        app.state.supervisor_client = supervisor_client
        app.state.latest_api_metrics = {
            "rps": 0.57,
            "latency_ms_p95": 5134.0,
            "error_rate": 0.118,
            "inflight": 1,
        }
        app.include_router(build_supervisors_router(self.store, self.enrollment_store), prefix="/api/system")
        client = TestClient(app)

        listed = client.get("/api/system/supervisors", headers={"X-Admin-Token": "test-token"})
        listed_again = client.get("/api/system/supervisors", headers={"X-Admin-Token": "test-token"})

        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed_again.status_code, 200, listed_again.text)
        items = listed.json()["items"]
        self.assertEqual(items[0]["supervisor_id"], "local-core-supervisor")
        self.assertEqual(items[0]["transport"], "local")
        self.assertEqual(items[0]["freshness_state"], "online")
        self.assertEqual(items[0]["registered_runtime_count"], 1)
        self.assertEqual(items[0]["core_runtime_count"], 1)
        self.assertTrue(items[0]["metadata"]["attached_to_core"])
        resource_usage = items[0]["core_runtimes"][0]["resource_usage"]
        self.assertEqual(resource_usage["rps"], 0.57)
        self.assertEqual(resource_usage["latency_ms_p95"], 5134.0)
        self.assertEqual(resource_usage["error_rate"], 0.118)
        self.assertEqual(resource_usage["inflight"], 1)
        self.assertEqual(len(supervisor_client.requests), 5)

    def test_local_supervisor_sorts_before_remote_supervisors(self) -> None:
        headers = {"X-Admin-Token": "test-token"}
        remote = self.client.post(
            "/api/system/supervisors/register",
            headers=headers,
            json={"supervisor_id": "aaa-remote", "transport": "socket"},
        )
        self.assertEqual(remote.status_code, 200, remote.text)
        local = self.client.post(
            "/api/system/supervisors/register",
            headers=headers,
            json={
                "supervisor_id": "zzz-local",
                "transport": "local",
                "metadata": {"attached_to_core": True},
            },
        )
        self.assertEqual(local.status_code, 200, local.text)

        listed = self.client.get("/api/system/supervisors", headers=headers)

        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual([item["supervisor_id"] for item in listed.json()["items"]], ["zzz-local", "aaa-remote"])

    def test_list_hides_long_offline_remote_supervisors_by_default(self) -> None:
        headers = {"X-Admin-Token": "test-token"}
        old_seen = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        for supervisor_id in ["old-remote", "fresh-remote"]:
            created = self.client.post(
                "/api/system/supervisors/register",
                headers=headers,
                json={"supervisor_id": supervisor_id, "transport": "http"},
            )
            self.assertEqual(created.status_code, 200, created.text)
            record = self.store.get(supervisor_id)
            self.assertIsNotNone(record)
            record.last_seen_at = old_seen if supervisor_id == "old-remote" else datetime.now(timezone.utc).isoformat()
            record.updated_at = record.last_seen_at
        self.store._save()

        listed = self.client.get("/api/system/supervisors", headers=headers)
        listed_with_history = self.client.get("/api/system/supervisors?include_historical=true", headers=headers)

        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual([item["supervisor_id"] for item in listed.json()["items"]], ["fresh-remote"])
        self.assertEqual(listed.json()["hidden_historical_count"], 1)
        self.assertEqual(listed_with_history.status_code, 200, listed_with_history.text)
        items_by_id = {item["supervisor_id"]: item for item in listed_with_history.json()["items"]}
        self.assertEqual(items_by_id["old-remote"]["visibility_state"], "historical")
        self.assertEqual(items_by_id["fresh-remote"]["visibility_state"], "active")

    def test_list_keeps_local_attached_supervisor_even_when_last_seen_is_old(self) -> None:
        headers = {"X-Admin-Token": "test-token"}
        created = self.client.post(
            "/api/system/supervisors/register",
            headers=headers,
            json={
                "supervisor_id": "local-core-supervisor",
                "transport": "local",
                "metadata": {"attached_to_core": True},
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        record = self.store.get("local-core-supervisor")
        self.assertIsNotNone(record)
        old_seen = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        record.last_seen_at = old_seen
        record.updated_at = old_seen
        self.store._save()

        listed = self.client.get("/api/system/supervisors", headers=headers)

        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["items"][0]["supervisor_id"], "local-core-supervisor")
        self.assertEqual(listed.json()["items"][0]["visibility_state"], "active")
        self.assertEqual(listed.json()["hidden_historical_count"], 0)

    def test_list_hides_superseded_old_local_supervisor_records(self) -> None:
        headers = {"X-Admin-Token": "test-token"}
        old_seen = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        current_seen = datetime.now(timezone.utc).isoformat()
        for supervisor_id, seen in [("Hexe", old_seen), ("hxe-supervisor", current_seen)]:
            created = self.client.post(
                "/api/system/supervisors/register",
                headers=headers,
                json={
                    "supervisor_id": supervisor_id,
                    "host_id": "Hexe",
                    "hostname": "Hexe",
                    "transport": "local",
                    "metadata": {"attached_to_core": True},
                },
            )
            self.assertEqual(created.status_code, 200, created.text)
            record = self.store.get(supervisor_id)
            self.assertIsNotNone(record)
            record.last_seen_at = seen
            record.updated_at = seen
        self.store._save()

        listed = self.client.get("/api/system/supervisors", headers=headers)
        listed_with_history = self.client.get("/api/system/supervisors?include_historical=true", headers=headers)

        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual([item["supervisor_id"] for item in listed.json()["items"]], ["hxe-supervisor"])
        self.assertEqual(listed.json()["hidden_historical_count"], 1)
        items_by_id = {item["supervisor_id"]: item for item in listed_with_history.json()["items"]}
        self.assertEqual(items_by_id["Hexe"]["visibility_state"], "historical")
        self.assertEqual(items_by_id["hxe-supervisor"]["visibility_state"], "active")

    def test_local_supervisor_history_uses_configured_client(self) -> None:
        app = FastAPI()
        supervisor_client = _FakeSupervisorClient()
        app.state.supervisor_client = supervisor_client
        app.include_router(build_supervisors_router(self.store, self.enrollment_store), prefix="/api/system")
        client = TestClient(app)
        headers = {"X-Admin-Token": "test-token"}

        host_history = client.get(
            "/api/system/supervisors/local-core-supervisor/resources/history?range=1h&step=60s",
            headers=headers,
        )
        runtime_history = client.get(
            "/api/system/supervisors/local-core-supervisor/runtimes/local-node/resources/history?range=1h",
            headers=headers,
        )
        core_runtime_history = client.get(
            "/api/system/supervisors/local-core-supervisor/core/runtimes/core-api/resources/history?range=1h",
            headers=headers,
        )

        self.assertEqual(host_history.status_code, 200, host_history.text)
        self.assertEqual(runtime_history.status_code, 200, runtime_history.text)
        self.assertEqual(core_runtime_history.status_code, 200, core_runtime_history.text)
        self.assertEqual(host_history.json()["scope"], "host")
        self.assertEqual(runtime_history.json()["resource_id"], "local-node")
        self.assertEqual(core_runtime_history.json()["resource_id"], "core-api")
        self.assertIn(("GET", "/api/supervisor/resources/history"), supervisor_client.requests)
        self.assertIn(("GET", "/api/supervisor/runtimes/local-node/resources/history"), supervisor_client.requests)
        self.assertIn(("GET", "/api/supervisor/core/runtimes/core-api/resources/history"), supervisor_client.requests)

    def test_remote_supervisor_history_uses_registered_api_base_url(self) -> None:
        headers = {"X-Admin-Token": "test-token"}
        registered = self.client.post(
            "/api/system/supervisors/register",
            headers=headers,
            json={
                "supervisor_id": "host-remote",
                "api_base_url": "http://remote-supervisor:57665",
                "transport": "http",
            },
        )
        self.assertEqual(registered.status_code, 200, registered.text)
        calls: list[tuple[str, dict[str, str]]] = []

        def fake_get(url: str, *, params: dict[str, str], timeout: float) -> httpx.Response:
            calls.append((url, params))
            return httpx.Response(200, json={"scope": "host", "samples": [], "timeout": timeout})

        with patch("app.system.supervisors.httpx.get", side_effect=fake_get):
            response = self.client.get(
                "/api/system/supervisors/host-remote/resources/history?range=24h&step=60s",
                headers=headers,
            )
            core_response = self.client.get(
                "/api/system/supervisors/host-remote/core/runtimes/core-api/resources/history?range=24h",
                headers=headers,
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(core_response.status_code, 200, core_response.text)
        self.assertEqual(response.json()["scope"], "host")
        self.assertEqual(calls[0][0], "http://remote-supervisor:57665/api/supervisor/resources/history")
        self.assertEqual(calls[0][1], {"range": "24h", "step": "60s"})
        self.assertEqual(calls[1][0], "http://remote-supervisor:57665/api/supervisor/core/runtimes/core-api/resources/history")
        self.assertEqual(calls[1][1], {"range": "24h", "step": "60s"})


if __name__ == "__main__":
    unittest.main()
