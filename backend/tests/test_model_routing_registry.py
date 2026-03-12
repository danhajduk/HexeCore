import tempfile
import unittest
from pathlib import Path

from app.system.onboarding.model_routing_registry import ModelRoutingRegistryService, ModelRoutingRegistryStore


class TestModelRoutingRegistry(unittest.TestCase):
    def test_records_and_groups_provider_model_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ModelRoutingRegistryStore(path=Path(tmpdir) / "model_routing_registry.json")
            service = ModelRoutingRegistryService(store)
            records = service.record_provider_intelligence(
                node_id="node-123",
                provider_intelligence=[
                    {
                        "provider": "openai",
                        "available_models": [
                            {
                                "model_id": "gpt-4o-mini",
                                "normalized_model_id": "gpt-4o-mini",
                                "pricing": {"input_per_1k": 0.00015},
                                "latency_metrics": {"p50_ms": 120.0},
                            }
                        ],
                    }
                ],
                node_available=True,
                source="provider_capability_report",
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].provider, "openai")
            self.assertEqual(records[0].normalized_model_id, "gpt-4o-mini")
            self.assertTrue(records[0].node_available)

            grouped = service.list_grouped_by_node(node_id="node-123")
            self.assertEqual(len(grouped), 1)
            self.assertEqual(grouped[0]["node_id"], "node-123")
            self.assertTrue(grouped[0]["node_available"])
            self.assertEqual(grouped[0]["providers"][0]["provider"], "openai")
            self.assertEqual(grouped[0]["providers"][0]["models"][0]["normalized_model_id"], "gpt-4o-mini")


if __name__ == "__main__":
    unittest.main()
