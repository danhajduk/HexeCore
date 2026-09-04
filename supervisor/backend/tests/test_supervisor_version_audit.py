from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from app.system.supervisor_version_audit import (
    SupervisorVersionAudit,
    SupervisorVersionAuditConfig,
    supervisor_version_audit_loop,
)
from app.system.supervisors import SupervisorFleetStore, SupervisorHeartbeatRequest, SupervisorRegistrationRequest


class _FakeLocalSupervisorClient:
    def __init__(self, status: dict | None = None) -> None:
        self.status = status or {
            "supervisor_id": "local-core-supervisor",
            "reported_version": "0.6.0",
            "supported_modes": ["git", "core_host"],
            "update_state": "idle",
            "git": {"local_sha": "abc123", "update_available": False, "behind": 0},
        }
        self.requests: list[tuple[str, str]] = []

    def request_json(self, method: str, path: str, **_kwargs):  # noqa: ANN001
        self.requests.append((method, path))
        if path == "/api/supervisor/update/status":
            return dict(self.status)
        return None


class _FakeAuditStore:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record_sync(self, **kwargs):  # noqa: ANN001
        self.records.append(kwargs)


class TestSupervisorVersionAudit(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = SupervisorFleetStore(path=Path(self.tmpdir.name) / "supervisors.json")

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _register_local(self) -> None:
        self.store.register(
            SupervisorRegistrationRequest(
                supervisor_id="local-core-supervisor",
                supervisor_version="0.6.0",
                transport="local",
                metadata={"attached_to_core": True},
            )
        )

    def _register_online_remote(self, supervisor_id: str, *, api_base_url: str | None = "http://remote-supervisor:57665") -> None:
        self.store.register(
            SupervisorRegistrationRequest(
                supervisor_id=supervisor_id,
                supervisor_version="0.1.0",
                api_base_url=api_base_url,
                transport="http",
            )
        )
        self.store.heartbeat(SupervisorHeartbeatRequest(supervisor_id=supervisor_id, health_status="healthy"))

    def test_config_defaults_to_enabled_ten_minute_interval(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = SupervisorVersionAuditConfig.from_env()

        self.assertTrue(config.enabled)
        self.assertEqual(config.interval_s, 600.0)

    def test_config_reads_env_and_clamps_interval(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HEXE_SUPERVISOR_VERSION_AUDIT_ENABLED": "false",
                "HEXE_SUPERVISOR_VERSION_AUDIT_INTERVAL_S": "10",
            },
            clear=True,
        ):
            config = SupervisorVersionAuditConfig.from_env()

        self.assertFalse(config.enabled)
        self.assertEqual(config.interval_s, 60.0)

    def test_audit_classifies_local_current_and_remote_outdated(self) -> None:
        self._register_local()
        self._register_online_remote("host-remote")
        audit_store = _FakeAuditStore()
        calls: list[str] = []

        def fake_request(method: str, url: str, *, timeout: float) -> httpx.Response:  # noqa: ARG001
            calls.append(f"{method} {url}")
            return httpx.Response(
                200,
                json={
                    "supervisor_id": "host-remote",
                    "reported_version": "0.1.0",
                    "supported_modes": ["core_host"],
                    "update_state": "idle",
                    "git": {"local_sha": "old456", "update_available": False, "behind": 0},
                    "current_update": {"token": "plain-token", "output": "authorization: bearer secret"},
                },
            )

        with patch("app.system.supervisor_version_audit.httpx.request", side_effect=fake_request):
            result = SupervisorVersionAudit(
                self.store,
                local_client=_FakeLocalSupervisorClient(),
                audit_store=audit_store,
                timeout_s=1.0,
            ).run_once()

        self.assertEqual(result["counts"], {"current": 1, "outdated": 1})
        self.assertEqual(calls, ["GET http://remote-supervisor:57665/api/supervisor/update/status"])
        local = self.store.get("local-core-supervisor")
        remote = self.store.get("host-remote")
        self.assertIsNotNone(local)
        self.assertIsNotNone(remote)
        self.assertEqual(local.metadata["version_audit"]["classification"], "current")
        self.assertEqual(remote.metadata["version_audit"]["classification"], "outdated")
        self.assertEqual(remote.metadata["version_audit"]["reason"], "source_commit_differs_from_local")
        serialized = str(remote.metadata["update_status"])
        self.assertNotIn("plain-token", serialized)
        self.assertNotIn("bearer secret", serialized)
        self.assertIn("[REDACTED]", serialized)
        event_types = [record["event_type"] for record in audit_store.records]
        self.assertIn("supervisor_version_audit_started", event_types)
        self.assertIn("supervisor_version_classification_changed", event_types)
        self.assertIn("supervisor_version_audit_completed", event_types)

    def test_audit_fails_closed_for_stale_and_missing_api_base_url(self) -> None:
        stale = self.store.register(
            SupervisorRegistrationRequest(
                supervisor_id="host-stale",
                supervisor_version="0.1.0",
                api_base_url="http://stale-supervisor:57665",
                transport="http",
            )
        )
        stale.last_seen_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        self.store._save()
        self._register_online_remote("host-missing-api", api_base_url=None)

        with patch("app.system.supervisor_version_audit.httpx.request") as request:
            SupervisorVersionAudit(self.store, local_client=_FakeLocalSupervisorClient()).run_once()

        request.assert_not_called()
        stale_record = self.store.get("host-stale")
        missing_api = self.store.get("host-missing-api")
        self.assertEqual(stale_record.metadata["version_audit"]["classification"], "unreachable")
        self.assertEqual(stale_record.metadata["version_audit"]["reason"], "heartbeat_offline")
        self.assertEqual(missing_api.metadata["version_audit"]["classification"], "unreachable")
        self.assertEqual(missing_api.metadata["version_audit"]["reason"], "supervisor_api_base_url_missing")

    def test_audit_classifies_missing_update_api_as_unsupported(self) -> None:
        self._register_online_remote("host-unsupported")

        with patch(
            "app.system.supervisor_version_audit.httpx.request",
            return_value=httpx.Response(404, json={"detail": "not_found"}),
        ):
            SupervisorVersionAudit(self.store, local_client=_FakeLocalSupervisorClient()).run_once()

        record = self.store.get("host-unsupported")
        self.assertEqual(record.metadata["version_audit"]["classification"], "unsupported")
        self.assertEqual(record.metadata["version_audit"]["reason"], "supervisor_update_api_not_found")

    def test_audit_classifies_invalid_update_status_as_unknown(self) -> None:
        self._register_online_remote("host-invalid")

        with patch("app.system.supervisor_version_audit.httpx.request", return_value=httpx.Response(200, json=[])):
            SupervisorVersionAudit(self.store, local_client=_FakeLocalSupervisorClient()).run_once()

        record = self.store.get("host-invalid")
        self.assertEqual(record.metadata["version_audit"]["classification"], "unknown")
        self.assertEqual(record.metadata["version_audit"]["reason"], "supervisor_update_api_invalid_payload")

    def test_loop_runs_immediately_then_uses_configured_sleep(self) -> None:
        self._register_local()
        app = SimpleNamespace(
            state=SimpleNamespace(
                supervisor_fleet_store=self.store,
                supervisor_client=_FakeLocalSupervisorClient(),
                audit_store=_FakeAuditStore(),
            )
        )
        sleeps: list[float] = []

        async def fake_sleep(interval: float) -> None:
            sleeps.append(interval)
            raise asyncio.CancelledError()

        async def run_loop() -> None:
            with patch("app.system.supervisor_version_audit.asyncio.sleep", side_effect=fake_sleep):
                await supervisor_version_audit_loop(app, SupervisorVersionAuditConfig(enabled=True, interval_s=600.0))

        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(run_loop())

        local = self.store.get("local-core-supervisor")
        self.assertEqual(local.metadata["version_audit"]["classification"], "current")
        self.assertEqual(sleeps, [600.0])


if __name__ == "__main__":
    unittest.main()
