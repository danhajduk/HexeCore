import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.addons.models import AddonMeta, BackendAddon, RegisteredAddon
from app.addons.registry import AddonRegistry
from app.system.auth import ServiceTokenKeyStore
from app.system.mqtt.integration_state import MqttIntegrationStateStore
from app.system.mqtt.router import build_mqtt_router
from app.system.mqtt.runtime_boundary import BrokerRuntimeStatus


class _FakeSettingsStore:
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    async def get(self, key: str):
        return self._data.get(key)


class _FakeMqttManager:
    def __init__(self) -> None:
        self.connected = False
        self.restart_calls = 0
        self.stop_calls = 0

    async def status(self):
        return {"ok": True, "connected": self.connected, "restart_calls": self.restart_calls, "stop_calls": self.stop_calls}

    async def restart(self):
        self.restart_calls += 1
        self.connected = True
        return None

    async def stop(self):
        self.stop_calls += 1
        self.connected = False
        return None

    async def publish_test(self, topic: str | None = None, payload: dict | None = None):
        return {"ok": True, "topic": topic or "synthia/core/mqtt/info", "payload": payload or {}}


class _FakeRuntimeBoundary:
    def __init__(self) -> None:
        self.state = "stopped"
        self.provider = "embedded_mosquitto"
        self.ensure_running_calls = 0
        self.stop_calls = 0
        self.controlled_restart_calls = 0

    async def ensure_running(self) -> BrokerRuntimeStatus:
        self.ensure_running_calls += 1
        self.state = "running"
        return BrokerRuntimeStatus(provider=self.provider, state="running", healthy=True, degraded_reason=None)

    async def stop(self) -> BrokerRuntimeStatus:
        self.stop_calls += 1
        self.state = "stopped"
        return BrokerRuntimeStatus(provider=self.provider, state="stopped", healthy=False, degraded_reason="runtime_stopped")

    async def health_check(self) -> BrokerRuntimeStatus:
        healthy = self.state == "running"
        reason = None if healthy else "runtime_stopped"
        return BrokerRuntimeStatus(provider=self.provider, state=self.state, healthy=healthy, degraded_reason=reason)

    async def reload(self) -> BrokerRuntimeStatus:
        return await self.health_check()

    async def controlled_restart(self) -> BrokerRuntimeStatus:
        self.controlled_restart_calls += 1
        self.state = "running"
        return BrokerRuntimeStatus(provider=self.provider, state="running", healthy=True, degraded_reason=None)

    async def get_status(self) -> BrokerRuntimeStatus:
        return await self.health_check()


class _FakeRuntimeReconciler:
    def __init__(self) -> None:
        self.reasons: list[str] = []

    async def reconcile_authority(self, *, reason: str):
        self.reasons.append(reason)
        return {"ok": True, "status": "ok", "runtime_state": "running", "reason": reason}


class _FakeAuditStore:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def append_event(self, *, event_type: str, status: str, message: str | None = None, payload: dict | None = None):
        item = {
            "event_type": event_type,
            "status": status,
            "message": message,
            "payload": payload or {},
        }
        self.events.append(item)
        return item


class TestMqttRuntimeControlApi(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(os.environ, {"SYNTHIA_ADMIN_TOKEN": "test-token"}, clear=False)
        self.env_patch.start()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.settings = _FakeSettingsStore()
        self.key_store = ServiceTokenKeyStore(self.settings)
        self.state_store = MqttIntegrationStateStore(str(Path(self.tmpdir.name) / "mqtt_state.json"))
        self.registry = AddonRegistry(
            addons={
                "vision": BackendAddon(
                    meta=AddonMeta(id="vision", name="Vision", version="1.0.0"),
                    router=APIRouter(),
                )
            },
            errors={},
            enabled={"vision": True},
            registered={
                "mqtt": RegisteredAddon(
                    id="mqtt",
                    name="MQTT",
                    version="1.0.0",
                    base_url="http://mqtt-addon.local:9100",
                )
            },
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        self.env_patch.stop()

    def _client(
        self,
        *,
        manager: _FakeMqttManager,
        runtime_boundary=None,
        runtime_reconciler=None,
        audit_store=None,
    ) -> TestClient:
        app = FastAPI()
        app.include_router(
            build_mqtt_router(
                manager,
                self.registry,
                self.state_store,
                self.key_store,
                runtime_boundary=runtime_boundary,
                runtime_reconciler=runtime_reconciler,
                audit_store=audit_store,
            ),
            prefix="/api/system",
        )
        return TestClient(app)

    def test_runtime_start_stop_and_health(self) -> None:
        manager = _FakeMqttManager()
        runtime = _FakeRuntimeBoundary()
        audit = _FakeAuditStore()
        client = self._client(manager=manager, runtime_boundary=runtime, runtime_reconciler=_FakeRuntimeReconciler(), audit_store=audit)

        health = client.get("/api/system/mqtt/runtime/health", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["runtime"]["state"], "stopped")

        start = client.post("/api/system/mqtt/runtime/start", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(start.status_code, 200, start.text)
        self.assertTrue(start.json()["ok"])
        self.assertEqual(start.json()["runtime"]["state"], "running")
        self.assertEqual(manager.restart_calls, 1)

        stop = client.post("/api/system/mqtt/runtime/stop", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(stop.status_code, 200, stop.text)
        self.assertTrue(stop.json()["ok"])
        self.assertEqual(stop.json()["runtime"]["state"], "stopped")
        self.assertEqual(manager.stop_calls, 1)

        actions = [item["payload"].get("action") for item in audit.events if item.get("event_type") == "mqtt_runtime_control"]
        self.assertIn("start", actions)
        self.assertIn("stop", actions)

    def test_runtime_init_and_rebuild_call_reconciler(self) -> None:
        manager = _FakeMqttManager()
        runtime = _FakeRuntimeBoundary()
        reconciler = _FakeRuntimeReconciler()
        client = self._client(
            manager=manager,
            runtime_boundary=runtime,
            runtime_reconciler=reconciler,
            audit_store=_FakeAuditStore(),
        )

        init_resp = client.post("/api/system/mqtt/runtime/init", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(init_resp.status_code, 200, init_resp.text)
        self.assertTrue(init_resp.json()["ok"])
        self.assertEqual(init_resp.json()["action"], "init")

        rebuild_resp = client.post("/api/system/mqtt/runtime/rebuild", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(rebuild_resp.status_code, 200, rebuild_resp.text)
        self.assertTrue(rebuild_resp.json()["ok"])
        self.assertEqual(rebuild_resp.json()["action"], "rebuild")

        self.assertIn("api_runtime_init", reconciler.reasons)
        self.assertIn("api_runtime_rebuild", reconciler.reasons)

    def test_runtime_control_requires_runtime_boundary(self) -> None:
        manager = _FakeMqttManager()
        client = self._client(manager=manager, runtime_boundary=None, runtime_reconciler=None, audit_store=None)

        start = client.post("/api/system/mqtt/runtime/start", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(start.status_code, 503, start.text)
        self.assertEqual(start.json()["detail"], "runtime_boundary_unavailable")


if __name__ == "__main__":
    unittest.main()
