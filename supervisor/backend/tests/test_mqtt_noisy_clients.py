import asyncio
import tempfile
import unittest
from pathlib import Path

from app.system.mqtt.integration_models import MqttPrincipal
from app.system.mqtt.integration_state import MqttIntegrationStateStore
from app.system.mqtt.noisy_clients import MqttNoisyClientEvaluator
from app.system.mqtt.observability_store import MqttObservabilityStore


class _FakeMqttManager:
    async def status(self):
        return {
            "ok": True,
            "connected": True,
            "connection_count": 24,
            "auth_failures": 6,
            "reconnect_spikes": 5,
        }

    async def principal_traffic_metrics(self):
        return {
            "addon:vision": {
                "messages_per_second": 240,
                "payload_size": 4096,
                "topic_count": 5,
            }
        }


class TestMqttNoisyClientEvaluator(unittest.TestCase):
    def test_noisy_evaluation_updates_principal_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_store = MqttIntegrationStateStore(str(Path(tmp) / "state.json"))
            obsv = MqttObservabilityStore(str(Path(tmp) / "obsv.db"))
            asyncio.run(
                state_store.upsert_principal(
                    MqttPrincipal(
                        principal_id="addon:vision",
                        principal_type="synthia_addon",
                        status="active",
                        logical_identity="vision",
                        linked_addon_id="vision",
                    )
                )
            )
            asyncio.run(
                obsv.append_event(
                    event_type="denied_topic_attempt",
                    source="mqtt_approval",
                    severity="warn",
                    metadata={"addon_id": "vision"},
                )
            )
            evaluator = MqttNoisyClientEvaluator(
                state_store=state_store,
                mqtt_manager=_FakeMqttManager(),
                observability_store=obsv,
            )
            result = asyncio.run(evaluator.evaluate())
            self.assertTrue(result["ok"])
            state = asyncio.run(state_store.get_state())
            principal = state.principals["addon:vision"]
            self.assertEqual(principal.noisy_state, "noisy")
            self.assertGreaterEqual(int(principal.noisy_inputs.get("auth_failures") or 0), 1)
            self.assertGreaterEqual(int(principal.noisy_inputs.get("messages_per_second") or 0), 200)


if __name__ == "__main__":
    unittest.main()
