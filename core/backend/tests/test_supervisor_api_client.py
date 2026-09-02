from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import os

import httpx

from app.supervisor.client import SupervisorApiClient, SupervisorClientConfig, supervisor_client_config
from app.supervisor.runtime_store import SupervisorRuntimeNodesStore


class TestSupervisorApiClient(unittest.TestCase):
    def test_supervisor_client_config_accepts_legacy_synthia_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SYNTHIA_SUPERVISOR_API_TRANSPORT": "http",
                "SYNTHIA_SUPERVISOR_API_BASE_URL": "10.0.0.55:57665",
                "SYNTHIA_SUPERVISOR_API_SOCKET": "/tmp/legacy-supervisor.sock",
                "SYNTHIA_SUPERVISOR_API_TIMEOUT_S": "7.5",
            },
            clear=True,
        ):
            config = supervisor_client_config()
        self.assertEqual(config.transport, "http")
        self.assertEqual(config.base_url, "http://10.0.0.55:57665")
        self.assertEqual(config.unix_socket, "/tmp/legacy-supervisor.sock")
        self.assertEqual(config.timeout_s, 7.5)

    def test_supervisor_client_requests(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/supervisor/admission":
                params = dict(request.url.params)
                assert params.get("total_capacity_units") == "50"
                assert params.get("reserve_units") == "5"
                return httpx.Response(
                    200,
                    json={
                        "admission_state": "ready",
                        "execution_host_ready": True,
                        "unavailable_reason": None,
                        "host_busy_rating": 1,
                        "total_capacity_units": 50,
                        "available_capacity_units": 25,
                        "managed_node_count": 1,
                        "healthy_managed_node_count": 1,
                    },
                )
            if request.url.path == "/api/supervisor/runtimes":
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "node_id": "node-1",
                                "node_name": "office-node",
                                "node_type": "ai",
                                "desired_state": "running",
                                "runtime_state": "running",
                                "lifecycle_state": "running",
                                "health_status": "healthy",
                                "freshness_state": "online",
                            }
                        ]
                    },
                )
            if request.url.path == "/api/supervisor/resources/history":
                params = dict(request.url.params)
                assert params.get("range") == "1h"
                assert params.get("step") == "60s"
                return httpx.Response(200, json={"scope": "host", "samples": [{"metrics": {"memory_percent": 42.0}}]})
            if request.url.path == "/api/supervisor/runtimes/node-1/resources/history":
                params = dict(request.url.params)
                assert params.get("range") == "1h"
                return httpx.Response(200, json={"scope": "runtime", "resource_id": "node-1", "samples": []})
            if request.url.path == "/api/supervisor/core/runtimes/core-api/resources/history":
                params = dict(request.url.params)
                assert params.get("range") == "1h"
                return httpx.Response(200, json={"scope": "core_runtime", "resource_id": "core-api", "samples": []})
            if request.url.path == "/api/supervisor/update/status":
                return httpx.Response(200, json={"supported_modes": ["git"], "update_state": "idle"})
            if request.url.path == "/api/supervisor/update/start":
                payload = request.read().decode("utf-8")
                assert "client-test-key" in payload
                return httpx.Response(200, json={"accepted": True, "state": "running"})
            if request.url.path == "/api/supervisor/runtime/cloudflared":
                return httpx.Response(200, json={"exists": True})
            if request.url.path == "/api/supervisor/runtime/cloudflared/apply":
                return httpx.Response(200, json={"ok": True, "runtime_state": "configured"})
            if request.url.path == "/api/supervisor/core/runtimes":
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "runtime_id": "core-api",
                                "runtime_name": "Hexe Core API",
                                "runtime_kind": "core_service",
                                "management_mode": "monitor",
                                "desired_state": "running",
                                "runtime_state": "running",
                                "lifecycle_state": "running",
                                "health_status": "healthy",
                                "freshness_state": "online",
                            }
                        ]
                    },
                )
            if request.url.path == "/api/supervisor/core/runtimes/register":
                return httpx.Response(
                    200,
                    json={
                        "runtime_id": "core-api",
                        "runtime_name": "Hexe Core API",
                        "runtime_kind": "core_service",
                        "management_mode": "monitor",
                        "desired_state": "running",
                        "runtime_state": "running",
                        "lifecycle_state": "running",
                        "health_status": "healthy",
                        "freshness_state": "online",
                    },
                )
            if request.url.path == "/api/supervisor/core/runtimes/heartbeat":
                return httpx.Response(
                    200,
                    json={
                        "runtime_id": "core-api",
                        "runtime_name": "Hexe Core API",
                        "runtime_kind": "core_service",
                        "management_mode": "monitor",
                        "desired_state": "running",
                        "runtime_state": "running",
                        "lifecycle_state": "running",
                        "health_status": "healthy",
                        "freshness_state": "online",
                    },
                )
            return httpx.Response(404, json={"detail": "not_found"})

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(transport=transport, base_url="http://supervisor")
        config = SupervisorClientConfig(
            transport="http",
            base_url="http://supervisor",
            unix_socket="/run/hexe/supervisor.sock",
            timeout_s=2.0,
        )
        client = SupervisorApiClient(config=config, client=http_client)

        admission = client.admission_summary(total_capacity_units=50, reserve_units=5, headroom_pct=0.05)
        self.assertIsNotNone(admission)
        self.assertEqual(admission.total_capacity_units, 50)

        runtimes = client.list_registered_runtimes()
        self.assertIsNotNone(runtimes)
        self.assertEqual(runtimes[0].node_id, "node-1")

        host_history = client.resource_history(range_value="1h", step_value="60s")
        self.assertEqual(host_history["scope"], "host")

        runtime_history = client.runtime_resource_history("node-1", range_value="1h", step_value=None)
        self.assertEqual(runtime_history["resource_id"], "node-1")

        core_runtime_history = client.core_runtime_resource_history("core-api", range_value="1h", step_value=None)
        self.assertEqual(core_runtime_history["resource_id"], "core-api")

        update_status = client.supervisor_update_status()
        self.assertEqual(update_status["supported_modes"], ["git"])

        update_result = client.start_supervisor_update({"source_mode": "git", "idempotency_key": "client-test-key"})
        self.assertTrue(update_result["accepted"])

        runtime_state = client.get_runtime_state("cloudflared")
        self.assertTrue(runtime_state["exists"])

        apply_result = client.apply_cloudflared_config({"rendered": True})
        self.assertTrue(apply_result["ok"])

        core_created = client.register_core_runtime({"runtime_id": "core-api", "runtime_name": "Hexe Core API"})
        self.assertIsNotNone(core_created)
        self.assertEqual(core_created.runtime_id, "core-api")

        core_heartbeat = client.heartbeat_core_runtime({"runtime_id": "core-api"})
        self.assertIsNotNone(core_heartbeat)
        self.assertEqual(core_heartbeat.runtime_name, "Hexe Core API")

        core_runtimes = client.list_core_runtimes()
        self.assertIsNotNone(core_runtimes)
        self.assertEqual(core_runtimes[0].runtime_id, "core-api")

        with tempfile.TemporaryDirectory() as tmp:
            store = SupervisorRuntimeNodesStore(path=Path(tmp) / "runtime.json")
            self.assertTrue(client.refresh_runtime_store(store))
            self.assertIsNotNone(store.get("node-1"))


if __name__ == "__main__":
    unittest.main()
