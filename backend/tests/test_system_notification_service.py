from __future__ import annotations

import unittest
from typing import Any

from app.core import CoreSystemNotificationService


class _FakeNotificationPublisher:
    def __init__(self) -> None:
        self.event_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.state_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def publish_internal_event(self, payload: dict[str, Any], *, qos: int = 1) -> dict[str, Any]:
        self.event_calls.append((payload, {"qos": qos}))
        return {"ok": True, "topic": "hexe/notify/internal/event", "message_id": "event-1"}

    async def publish_internal_state(
        self,
        payload: dict[str, Any],
        *,
        qos: int = 1,
        retain: bool = False,
    ) -> dict[str, Any]:
        self.state_calls.append((payload, {"qos": qos, "retain": retain}))
        return {"ok": True, "topic": "hexe/notify/internal/state", "message_id": "state-1"}


class TestSystemNotificationService(unittest.IsolatedAsyncioTestCase):
    async def test_emit_system_online_targets_home_assistant(self) -> None:
        publisher = _FakeNotificationPublisher()
        service = CoreSystemNotificationService(publisher, core_version="0.1.0")

        result = await service.emit_system_online(
            component="startup",
            message="Hexe Core startup complete and Home Assistant notifications are active.",
        )

        self.assertTrue(result["ok"])
        payload = publisher.state_calls[0][0]
        self.assertEqual(payload["targets"], {"external": ["ha"]})
        self.assertEqual(payload["delivery"]["severity"], "success")
        self.assertEqual(payload["delivery"]["urgency"], "notification")
        self.assertEqual(payload["state"]["status"], "online")
        self.assertEqual(payload["source"]["component"], "startup")
        self.assertTrue(publisher.state_calls[0][1]["retain"])

    async def test_emit_system_warning_marks_actions_needed(self) -> None:
        publisher = _FakeNotificationPublisher()
        service = CoreSystemNotificationService(publisher, core_version="0.1.0")

        await service.emit_system_warning(
            component="mqtt_runtime",
            message="Hexe Core MQTT runtime warning: broker disconnected",
            dedupe_key="core-mqtt-runtime-warning",
            data={"provider": "docker"},
        )

        payload = publisher.event_calls[0][0]
        self.assertEqual(payload["delivery"]["severity"], "warning")
        self.assertEqual(payload["delivery"]["priority"], "high")
        self.assertEqual(payload["delivery"]["urgency"], "actions_needed")
        self.assertEqual(payload["delivery"]["dedupe_key"], "core-mqtt-runtime-warning")
        self.assertEqual(payload["event"]["event_type"], "core_system_warning")
        self.assertEqual(payload["data"]["provider"], "docker")

    async def test_emit_system_error_marks_urgent(self) -> None:
        publisher = _FakeNotificationPublisher()
        service = CoreSystemNotificationService(publisher, core_version="0.1.0")

        await service.emit_system_error(
            component="mqtt_runtime_supervisor",
            message="Hexe Core MQTT runtime supervision error: RuntimeError: boom",
            dedupe_key="core-mqtt-runtime-error",
            data={"error_type": "RuntimeError"},
        )

        payload = publisher.event_calls[0][0]
        self.assertEqual(payload["targets"], {"external": ["ha"]})
        self.assertEqual(payload["delivery"]["severity"], "error")
        self.assertEqual(payload["delivery"]["priority"], "urgent")
        self.assertEqual(payload["delivery"]["urgency"], "urgent")
        self.assertEqual(payload["event"]["event_type"], "core_system_error")
        self.assertEqual(payload["source"]["component"], "mqtt_runtime_supervisor")
        self.assertEqual(payload["data"]["error_type"], "RuntimeError")


if __name__ == "__main__":
    unittest.main()
