from __future__ import annotations

import unittest
from typing import Any

from app.core import NODE_DOMAIN_EVENT_TOPIC_FILTER, NodeDomainEventPromoterService
from app.system.mqtt.integration_models import MqttIntegrationState, MqttPrincipal


class _FakeMqttManager:
    def __init__(self) -> None:
        self.listeners: dict[str, tuple[str, Any]] = {}
        self.counter = 0
        self.publish_calls: list[dict[str, Any]] = []

    def register_message_listener(self, *, topic_filter: str, callback):
        self.counter += 1
        listener_id = f"listener-{self.counter}"
        self.listeners[listener_id] = (topic_filter, callback)
        return listener_id

    def unregister_message_listener(self, listener_id: str) -> bool:
        return self.listeners.pop(listener_id, None) is not None

    async def publish(self, topic: str, payload: dict[str, Any], retain: bool = True, qos: int = 1) -> dict[str, Any]:
        self.publish_calls.append({"topic": topic, "payload": payload, "retain": retain, "qos": qos})
        return {"ok": True, "topic": topic, "rc": 0}


class _FakeStateStore:
    def __init__(self, state: MqttIntegrationState) -> None:
        self._state = state

    async def get_state(self) -> MqttIntegrationState:
        return self._state


class _FakeObservabilityStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def append_event(self, *, event_type: str, source: str, severity: str = "info", metadata=None) -> dict[str, Any]:
        item = {
            "event_type": event_type,
            "source": source,
            "severity": severity,
            "metadata": metadata or {},
        }
        self.events.append(item)
        return item


class TestNodeDomainEventPromoter(unittest.IsolatedAsyncioTestCase):
    def _state(self) -> MqttIntegrationState:
        return MqttIntegrationState(
            principals={
                "node:email-node-1": MqttPrincipal(
                    principal_id="node:email-node-1",
                    principal_type="synthia_node",
                    status="active",
                    logical_identity="email-node-1",
                    linked_node_id="email-node-1",
                    username="hn_email-node-1",
                    publish_topics=["hexe/nodes/email-node-1/#"],
                    subscribe_topics=["hexe/bootstrap/core", "hexe/events/#", "hexe/nodes/email-node-1/#"],
                )
            }
        )

    def _payload(self, **overrides) -> dict[str, Any]:
        payload = {
            "event_id": "evt-1",
            "event_type": "delivery.window.upserted",
            "source": {"node_id": "email-node-1", "component": "email-parser", "node_type": "email-node"},
            "subject": {"family": "delivery", "message_id": "msg-1"},
            "data": {
                "message_id": "msg-1",
                "sender_domain": "doordash.com",
                "delivery_window": {"starts_at": "2026-05-02T18:00:00+00:00"},
            },
        }
        payload.update(overrides)
        return payload

    async def test_registers_node_domain_event_filter(self) -> None:
        mqtt = _FakeMqttManager()
        service = NodeDomainEventPromoterService(mqtt, _FakeStateStore(self._state()), _FakeObservabilityStore())

        await service.start()

        self.assertEqual([item[0] for item in mqtt.listeners.values()], [NODE_DOMAIN_EVENT_TOPIC_FILTER])

    async def test_promotes_valid_event_to_source_and_domain_topics(self) -> None:
        mqtt = _FakeMqttManager()
        observability = _FakeObservabilityStore()
        service = NodeDomainEventPromoterService(mqtt, _FakeStateStore(self._state()), observability, core_id="core-test")

        await service._handle_runtime_message(
            "hexe/nodes/email-node-1/events/delivery/window/upserted",
            self._payload(),
            False,
        )

        self.assertEqual([call["topic"] for call in mqtt.publish_calls], [
            "hexe/events/nodes/email-node-1/delivery/window/upserted",
            "hexe/events/delivery/window/upserted",
        ])
        promoted = mqtt.publish_calls[0]["payload"]
        self.assertEqual(promoted["promoted_event_type"], "delivery.window.upserted")
        self.assertEqual(promoted["source"]["node_id"], "email-node-1")
        self.assertEqual(promoted["core"]["core_id"], "core-test")
        self.assertEqual(promoted["core"]["validation_status"], "accepted")
        self.assertEqual(promoted["routing"]["domain_topic"], "hexe/events/delivery/window/upserted")
        self.assertFalse(mqtt.publish_calls[0]["retain"])
        self.assertEqual(observability.events[-1]["metadata"]["decision"], "accepted")

    async def test_rejects_retained_events(self) -> None:
        mqtt = _FakeMqttManager()
        observability = _FakeObservabilityStore()
        service = NodeDomainEventPromoterService(mqtt, _FakeStateStore(self._state()), observability)

        await service._handle_runtime_message(
            "hexe/nodes/email-node-1/events/delivery/window/upserted",
            self._payload(),
            True,
        )

        self.assertEqual(mqtt.publish_calls, [])
        self.assertEqual(observability.events[-1]["metadata"]["decision"], "rejected")
        self.assertEqual(observability.events[-1]["metadata"]["reason"], "retained_events_not_supported")

    async def test_rejects_node_id_mismatch(self) -> None:
        mqtt = _FakeMqttManager()
        observability = _FakeObservabilityStore()
        service = NodeDomainEventPromoterService(mqtt, _FakeStateStore(self._state()), observability)

        await service._handle_runtime_message(
            "hexe/nodes/email-node-1/events/delivery/window/upserted",
            self._payload(source={"node_id": "other-node", "component": "email-parser"}),
            False,
        )

        self.assertEqual(mqtt.publish_calls, [])
        self.assertEqual(observability.events[-1]["metadata"]["reason"], "node_id_topic_mismatch")

    async def test_redacts_secret_fields_before_promotion(self) -> None:
        mqtt = _FakeMqttManager()
        observability = _FakeObservabilityStore()
        service = NodeDomainEventPromoterService(mqtt, _FakeStateStore(self._state()), observability)

        payload = self._payload(data={"message_id": "msg-1", "api_key": "secret-value", "sender_domain": "doordash.com"})
        await service._handle_runtime_message(
            "hexe/nodes/email-node-1/events/delivery/window/upserted",
            payload,
            False,
        )

        promoted = mqtt.publish_calls[0]["payload"]
        self.assertEqual(promoted["data"]["api_key"], "[REDACTED]")
        self.assertEqual(promoted["core"]["validation_status"], "accepted_with_redaction")
        self.assertEqual(observability.events[-1]["metadata"]["decision"], "accepted_with_redaction")

    async def test_rejects_forbidden_raw_payload_fields(self) -> None:
        mqtt = _FakeMqttManager()
        observability = _FakeObservabilityStore()
        service = NodeDomainEventPromoterService(mqtt, _FakeStateStore(self._state()), observability)

        await service._handle_runtime_message(
            "hexe/nodes/email-node-1/events/delivery/window/upserted",
            self._payload(data={"raw_email_body": "full body"}),
            False,
        )

        self.assertEqual(mqtt.publish_calls, [])
        self.assertEqual(observability.events[-1]["metadata"]["reason"], "privacy_policy_rejected")
        self.assertEqual(observability.events[-1]["metadata"]["noise_state"], "blocked")

    async def test_deduplicates_replayed_events(self) -> None:
        mqtt = _FakeMqttManager()
        observability = _FakeObservabilityStore()
        service = NodeDomainEventPromoterService(mqtt, _FakeStateStore(self._state()), observability)
        topic = "hexe/nodes/email-node-1/events/delivery/window/upserted"

        await service._handle_runtime_message(topic, self._payload(), False)
        await service._handle_runtime_message(topic, self._payload(), False)

        self.assertEqual(len(mqtt.publish_calls), 2)
        self.assertEqual(observability.events[-1]["metadata"]["decision"], "deduped")


if __name__ == "__main__":
    unittest.main()
