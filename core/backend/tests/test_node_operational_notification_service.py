from __future__ import annotations

import time
import unittest
from typing import Any

from app.core import NodeOperationalNotificationService
from app.system.onboarding import NodeRegistrationRecord, NodeRegistrationsStore


class _FakePublisher:
    def __init__(self) -> None:
        self.popup_calls: list[dict[str, Any]] = []
        self.event_calls: list[dict[str, Any]] = []

    async def publish_internal_popup(self, payload: dict[str, Any], *, qos: int = 1) -> dict[str, Any]:
        self.popup_calls.append(payload)
        return {"ok": True, "topic": "hexe/notify/internal/popup", "message_id": "popup-1"}

    async def publish_internal_event(self, payload: dict[str, Any], *, qos: int = 1) -> dict[str, Any]:
        self.event_calls.append(payload)
        return {"ok": True, "topic": "hexe/notify/internal/event", "message_id": "event-1"}


class _FakeMqttManager:
    def __init__(self, snapshot: dict[str, Any] | None) -> None:
        self.snapshot = snapshot

    async def node_runtime_snapshot(self, node_id: str) -> dict[str, Any] | None:
        return self.snapshot


class _FakeGovernanceStatusService:
    def get_status(self, node_id: str):
        return type(
            "Status",
            (),
            {
                "active_governance_version": "gov-1",
                "last_issued_timestamp": "2026-04-03T20:00:00+00:00",
                "last_refresh_request_timestamp": None,
                "freshness_changed_at": "2026-04-03T20:00:00+00:00",
            },
        )()

    def governance_freshness(self, node_id: str) -> dict[str, Any]:
        return {
            "state": "fresh",
            "changed_at": "2026-04-03T20:00:00+00:00",
            "stale_for_s": 0,
            "outdated": False,
        }


class TestNodeOperationalNotificationService(unittest.IsolatedAsyncioTestCase):
    def _registrations(self, *, trust_status: str = "trusted", capability_profile_id: str = "profile-1") -> NodeRegistrationsStore:
        store = NodeRegistrationsStore()
        store._records_by_node = {
            "node-1": NodeRegistrationRecord(
                node_id="node-1",
                node_type="ai-node",
                node_name="Vision Node",
                node_software_version="1.0.0",
                requested_node_type="ai-node",
                capabilities_summary=["vision"],
                trust_status=trust_status,
                source_onboarding_session_id="session-1",
                approved_by_user_id="admin",
                approved_at="2026-04-03T20:00:00+00:00",
                created_at="2026-04-03T20:00:00+00:00",
                updated_at="2026-04-03T20:00:00+00:00",
                capability_profile_id=capability_profile_id,
            )
        }
        return store

    async def test_emits_warning_when_trusted_operational_node_goes_offline(self) -> None:
        publisher = _FakePublisher()
        snapshot = {
            "reported_health_status": "healthy",
            "_last_status_report_epoch": time.time() - 1900,
        }
        service = NodeOperationalNotificationService(
            publisher,
            _FakeMqttManager(snapshot),
            self._registrations(),
            _FakeGovernanceStatusService(),
        )

        results = await service.poll_once()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "offline")
        self.assertEqual(len(publisher.popup_calls), 1)
        self.assertEqual(len(publisher.event_calls), 1)
        popup = publisher.popup_calls[0]
        self.assertTrue(popup["targets"]["broadcast"])
        self.assertEqual(popup["targets"]["external"], ["ha"])
        self.assertEqual(popup["delivery"]["channels"], ["popup", "event"])
        self.assertEqual(popup["event"]["action"], "offline")

    async def test_emits_warning_when_status_becomes_degraded(self) -> None:
        publisher = _FakePublisher()
        snapshot = {
            "reported_health_status": "healthy",
            "_last_status_report_epoch": time.time() - 400,
        }
        service = NodeOperationalNotificationService(
            publisher,
            _FakeMqttManager(snapshot),
            self._registrations(),
            _FakeGovernanceStatusService(),
        )

        results = await service.poll_once()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "degraded")
        self.assertEqual(publisher.event_calls[0]["delivery"]["urgency"], "actions_needed")

    async def test_does_not_repeat_same_warning_state(self) -> None:
        publisher = _FakePublisher()
        snapshot = {
            "reported_health_status": "healthy",
            "_last_status_report_epoch": time.time() - 1900,
        }
        service = NodeOperationalNotificationService(
            publisher,
            _FakeMqttManager(snapshot),
            self._registrations(),
            _FakeGovernanceStatusService(),
        )

        await service.poll_once()
        results = await service.poll_once()

        self.assertEqual(results, [])
        self.assertEqual(len(publisher.popup_calls), 1)
        self.assertEqual(len(publisher.event_calls), 1)

    async def test_skips_untrusted_or_not_operational_nodes(self) -> None:
        publisher = _FakePublisher()
        snapshot = {
            "reported_health_status": "healthy",
            "_last_status_report_epoch": time.time() - 1900,
        }
        service = NodeOperationalNotificationService(
            publisher,
            _FakeMqttManager(snapshot),
            self._registrations(trust_status="pending", capability_profile_id=None),
            _FakeGovernanceStatusService(),
        )

        results = await service.poll_once()

        self.assertEqual(results, [])
        self.assertEqual(publisher.popup_calls, [])
        self.assertEqual(publisher.event_calls, [])


if __name__ == "__main__":
    unittest.main()
