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
    SupervisorAutoUpdateConfig,
    SupervisorAutoUpdateTrigger,
    SupervisorVersionAudit,
    SupervisorVersionAuditConfig,
    SupervisorVersionReference,
    supervisor_version_audit_loop,
)
from app.system.supervisors import SupervisorFleetStore, SupervisorHeartbeatRequest, SupervisorRegistrationRequest


class _FakeLocalSupervisorClient:
    def __init__(self, status: dict | None = None) -> None:
        self.status = status or {
            "supervisor_id": "local-core-supervisor",
            "reported_version": "0.6.2",
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


class _FakeLocalSourceGate:
    def __init__(self, classification: str = "current", reason: str = "local_source_current") -> None:
        self.classification = classification
        self.reason = reason

    def inspect(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": "1",
            "classification": self.classification,
            "reason": self.reason,
            "auto_update_allowed": self.classification == "current",
            "source_root": "/tmp/repo/supervisor",
            "head": "abc123",
        }
        if self.classification != "current":
            result["auto_update_blocker"] = self.reason
        return result


class _FakePackage:
    def __init__(self, package_id: str = "pkg-test") -> None:
        self.package_id = package_id

    def to_request_payload(self) -> dict[str, object]:
        return {
            "package_id": self.package_id,
            "package_manifest": {"package_id": self.package_id},
            "package_archive_base64": "YXJjaGl2ZQ==",
            "package_archive_sha256": "sha256",
            "package_archive_size": 7,
        }


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
                supervisor_version="0.6.2",
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
                local_source_gate=_FakeLocalSourceGate(),
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
        self.assertEqual(remote.metadata["auto_update_decision"]["decision"], "recommended")
        self.assertEqual(remote.metadata["auto_update_decision"]["reason"], "auto_update_disabled")
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
            SupervisorVersionAudit(
                self.store,
                local_client=_FakeLocalSupervisorClient(),
                local_source_gate=_FakeLocalSourceGate(),
            ).run_once()

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
            SupervisorVersionAudit(
                self.store,
                local_client=_FakeLocalSupervisorClient(),
                local_source_gate=_FakeLocalSourceGate(),
            ).run_once()

        record = self.store.get("host-unsupported")
        self.assertEqual(record.metadata["version_audit"]["classification"], "unsupported")
        self.assertEqual(record.metadata["version_audit"]["reason"], "supervisor_update_api_not_found")

    def test_audit_classifies_invalid_update_status_as_unknown(self) -> None:
        self._register_online_remote("host-invalid")

        with patch("app.system.supervisor_version_audit.httpx.request", return_value=httpx.Response(200, json=[])):
            SupervisorVersionAudit(
                self.store,
                local_client=_FakeLocalSupervisorClient(),
                local_source_gate=_FakeLocalSourceGate(),
            ).run_once()

        record = self.store.get("host-invalid")
        self.assertEqual(record.metadata["version_audit"]["classification"], "unknown")
        self.assertEqual(record.metadata["version_audit"]["reason"], "supervisor_update_api_invalid_payload")

    def test_loop_runs_immediately_then_uses_configured_sleep(self) -> None:
        self._register_local()
        app = SimpleNamespace(
            state=SimpleNamespace(
                supervisor_fleet_store=self.store,
                supervisor_client=_FakeLocalSupervisorClient(),
                supervisor_local_source_gate=_FakeLocalSourceGate(),
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

    def test_audit_blocks_remote_currentness_when_local_source_gate_not_current(self) -> None:
        self._register_local()
        self._register_online_remote("host-remote")

        with patch(
            "app.system.supervisor_version_audit.httpx.request",
            return_value=httpx.Response(
                200,
                json={
                    "supervisor_id": "host-remote",
                    "reported_version": "0.6.2",
                    "supported_modes": ["core_host"],
                    "update_state": "idle",
                    "git": {"local_sha": "abc123", "behind": 0, "update_available": False},
                },
            ),
        ):
            result = SupervisorVersionAudit(
                self.store,
                local_client=_FakeLocalSupervisorClient(),
                local_source_gate=_FakeLocalSourceGate("behind", "local_behind_upstream"),
            ).run_once()

        self.assertEqual(result["local_source_gate"]["classification"], "behind")
        remote = self.store.get("host-remote")
        self.assertEqual(remote.metadata["local_source_gate"]["classification"], "behind")
        self.assertEqual(remote.metadata["version_audit"]["classification"], "unknown")
        self.assertEqual(remote.metadata["version_audit"]["reason"], "local_source_not_current")
        self.assertEqual(remote.metadata["version_audit"]["auto_update_blocker"], "local_behind_upstream")
        self.assertEqual(remote.metadata["auto_update_decision"]["decision"], "blocked")
        self.assertEqual(remote.metadata["auto_update_decision"]["reason"], "local_source_not_current")

    def _mark_remote_outdated(self, supervisor_id: str, *, supported_modes: list[str] | None = None) -> None:
        self._register_online_remote(supervisor_id)
        self.store.set_version_audit_status(
            supervisor_id,
            {
                "schema_version": "1",
                "supervisor_id": supervisor_id,
                "classification": "outdated",
                "reason": "source_commit_differs_from_local",
                "freshness_state": "online",
                "api_reachable": True,
                "reported_version": "0.1.0",
                "source_commit": "old456",
                "supported_modes": supported_modes or ["core_host"],
                "update_state": "idle",
            },
        )

    def _reference(self) -> SupervisorVersionReference:
        return SupervisorVersionReference(
            reported_version="0.6.2",
            source_commit="abc123",
            local_source_gate=_FakeLocalSourceGate().inspect(),
        )

    def test_auto_update_enabled_starts_remote_and_refreshes_status(self) -> None:
        self._mark_remote_outdated("host-remote")
        calls: list[tuple[str, str, dict | None]] = []

        def fake_request(method: str, url: str, *, json=None, timeout: float):  # noqa: ANN001, ARG001
            calls.append((method, url, json))
            if method == "POST":
                self.assertEqual(json["source_mode"], "core_host")
                self.assertEqual(json["package_id"], "pkg-test")
                return httpx.Response(200, json={"accepted": True, "request_id": "upd-1", "status": {"update_state": "starting"}})
            update_state = "running" if any(call[0] == "POST" for call in calls) else "idle"
            return httpx.Response(
                200,
                json={
                    "reported_version": "0.1.0",
                    "supported_modes": ["core_host"],
                    "update_state": update_state,
                    "git": {"local_sha": "old456"},
                    "current_update": {"request_id": "upd-1"} if update_state == "running" else None,
                },
            )

        summary = SupervisorAutoUpdateTrigger(
            self.store,
            config=SupervisorAutoUpdateConfig(enabled=True),
            http_request=fake_request,
            package_builder=lambda *_args, **_kwargs: _FakePackage(),
        ).run(self._reference(), local_source_gate=_FakeLocalSourceGate().inspect())

        self.assertEqual(summary["started"], 1)
        self.assertEqual([call[0] for call in calls], ["GET", "POST", "GET"])
        record = self.store.get("host-remote")
        self.assertEqual(record.metadata["auto_update_decision"]["decision"], "started")
        self.assertEqual(record.metadata["auto_update_decision"]["update_request_id"], "upd-1")
        self.assertEqual(record.metadata["update_status"]["update_state"], "running")

    def test_auto_update_allow_and_deny_filters(self) -> None:
        self._mark_remote_outdated("host-a")
        self._mark_remote_outdated("host-b")
        calls: list[str] = []

        def fake_request(method: str, url: str, *, json=None, timeout: float):  # noqa: ANN001, ARG001
            calls.append(f"{method} {url}")
            if method == "POST":
                return httpx.Response(200, json={"accepted": True, "request_id": "upd-allow"})
            return httpx.Response(200, json={"supported_modes": ["core_host"], "update_state": "idle"})

        SupervisorAutoUpdateTrigger(
            self.store,
            config=SupervisorAutoUpdateConfig(enabled=True, allowed_ids=frozenset({"host-a"}), denied_ids=frozenset({"host-b"})),
            http_request=fake_request,
            package_builder=lambda *_args, **_kwargs: _FakePackage(),
        ).run(self._reference(), local_source_gate=_FakeLocalSourceGate().inspect())

        self.assertEqual(self.store.get("host-a").metadata["auto_update_decision"]["decision"], "started")
        self.assertEqual(self.store.get("host-b").metadata["auto_update_decision"]["reason"], "supervisor_auto_update_denied")
        self.assertEqual(len([call for call in calls if call.startswith("POST ")]), 1)

    def test_auto_update_respects_max_parallel(self) -> None:
        self._mark_remote_outdated("host-a")
        self._mark_remote_outdated("host-b")
        calls: list[str] = []

        def fake_request(method: str, url: str, *, json=None, timeout: float):  # noqa: ANN001, ARG001
            calls.append(f"{method} {url}")
            if method == "POST":
                return httpx.Response(200, json={"accepted": True, "request_id": "upd-one"})
            return httpx.Response(200, json={"supported_modes": ["core_host"], "update_state": "idle"})

        summary = SupervisorAutoUpdateTrigger(
            self.store,
            config=SupervisorAutoUpdateConfig(enabled=True, max_parallel=1),
            http_request=fake_request,
            package_builder=lambda *_args, **_kwargs: _FakePackage(),
        ).run(self._reference(), local_source_gate=_FakeLocalSourceGate().inspect())

        self.assertEqual(summary["started"], 1)
        self.assertEqual(self.store.get("host-a").metadata["auto_update_decision"]["decision"], "started")
        self.assertEqual(self.store.get("host-b").metadata["auto_update_decision"]["reason"], "max_parallel_limit")
        self.assertEqual(len([call for call in calls if call.startswith("POST ")]), 1)

    def test_repeated_auto_update_does_not_start_duplicate_for_same_target(self) -> None:
        self._mark_remote_outdated("host-remote")
        calls: list[str] = []

        def fake_request(method: str, url: str, *, json=None, timeout: float):  # noqa: ANN001, ARG001
            calls.append(method)
            if method == "POST":
                return httpx.Response(200, json={"accepted": True, "request_id": "upd-idem"})
            return httpx.Response(200, json={"supported_modes": ["core_host"], "update_state": "idle"})

        trigger = SupervisorAutoUpdateTrigger(
            self.store,
            config=SupervisorAutoUpdateConfig(enabled=True),
            http_request=fake_request,
            package_builder=lambda *_args, **_kwargs: _FakePackage(),
        )
        trigger.run(self._reference(), local_source_gate=_FakeLocalSourceGate().inspect())
        first_key = self.store.get("host-remote").metadata["auto_update_decision"]["idempotency_key"]
        trigger.run(self._reference(), local_source_gate=_FakeLocalSourceGate().inspect())

        decision = self.store.get("host-remote").metadata["auto_update_decision"]
        self.assertEqual(decision["decision"], "skipped")
        self.assertEqual(decision["reason"], "already_triggered_for_target")
        self.assertEqual(decision["idempotency_key"], first_key)
        self.assertEqual(calls.count("POST"), 1)

    def test_auto_update_failure_backoff_blocks_retry(self) -> None:
        self._mark_remote_outdated("host-remote")
        calls: list[str] = []

        def failing_request(method: str, url: str, *, json=None, timeout: float):  # noqa: ANN001, ARG001
            calls.append(method)
            raise httpx.ConnectError("unreachable")

        trigger = SupervisorAutoUpdateTrigger(
            self.store,
            config=SupervisorAutoUpdateConfig(enabled=True),
            http_request=failing_request,
            package_builder=lambda *_args, **_kwargs: _FakePackage(),
        )
        trigger.run(self._reference(), local_source_gate=_FakeLocalSourceGate().inspect())
        trigger.run(self._reference(), local_source_gate=_FakeLocalSourceGate().inspect())

        decision = self.store.get("host-remote").metadata["auto_update_decision"]
        self.assertEqual(decision["decision"], "blocked")
        self.assertEqual(decision["reason"], "failure_backoff_active")
        self.assertEqual(calls, ["GET"])

    def test_auto_update_blocks_when_ble_pairing_session_active(self) -> None:
        self._mark_remote_outdated("host-remote")
        ble_sessions = SimpleNamespace(
            list_sessions=lambda: [
                SimpleNamespace(
                    status="waiting",
                    supervisor_id="host-remote",
                    supervisor_results=[],
                )
            ]
        )

        trigger = SupervisorAutoUpdateTrigger(
            self.store,
            config=SupervisorAutoUpdateConfig(enabled=True),
            ble_pairing_sessions=ble_sessions,
            http_request=lambda *_args, **_kwargs: self.fail("update API should not be called"),
            package_builder=lambda *_args, **_kwargs: _FakePackage(),
        )
        trigger.run(self._reference(), local_source_gate=_FakeLocalSourceGate().inspect())

        decision = self.store.get("host-remote").metadata["auto_update_decision"]
        self.assertEqual(decision["decision"], "blocked")
        self.assertEqual(decision["reason"], "ble_pairing_session_active")

    def test_auto_update_blocks_unsupported_mode(self) -> None:
        self._mark_remote_outdated("host-remote", supported_modes=["git"])

        trigger = SupervisorAutoUpdateTrigger(
            self.store,
            config=SupervisorAutoUpdateConfig(enabled=True, source_mode="core_host"),
            http_request=lambda *_args, **_kwargs: self.fail("update API should not be called"),
            package_builder=lambda *_args, **_kwargs: _FakePackage(),
        )
        trigger.run(self._reference(), local_source_gate=_FakeLocalSourceGate().inspect())

        decision = self.store.get("host-remote").metadata["auto_update_decision"]
        self.assertEqual(decision["decision"], "blocked")
        self.assertEqual(decision["reason"], "supervisor_update_mode_unsupported")


if __name__ == "__main__":
    unittest.main()
