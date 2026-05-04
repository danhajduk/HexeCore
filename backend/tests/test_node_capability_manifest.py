import unittest

from app.system.onboarding.capability_manifest import (
    CAPABILITY_DECLARATION_SCHEMA_VERSION,
    CapabilityManifestValidationError,
    validate_capability_declaration,
)


class TestNodeCapabilityManifest(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "manifest_version": CAPABILITY_DECLARATION_SCHEMA_VERSION,
            "node": {
                "node_id": "node-abc123",
                "node_type": "ai-node",
                "node_name": "main-ai-node",
                "node_software_version": "0.2.0",
            },
            "declared_task_families": ["task.classification", "task.summarization"],
            "declared_capabilities": ["task.classification", "task.summarization"],
            "capability_endpoints": {
                "task.summarization": {
                    "transport": "http",
                    "method": "POST",
                    "path": "/api/summarize",
                    "url": "http://ai-node.local:9002/api/summarize",
                }
            },
            "supported_providers": ["openai", "local-llm"],
            "enabled_providers": ["openai"],
            "provider_intelligence": [
                {
                    "provider": "openai",
                    "available_models": [
                        {
                            "model_id": "gpt-4o-mini",
                            "pricing": {"input_per_1k": 0.00015, "output_per_1k": 0.0006},
                            "latency_metrics": {"p50_ms": 120.0, "p95_ms": 280.0},
                        }
                    ],
                }
            ],
            "node_features": {
                "telemetry": True,
                "governance_refresh": True,
                "lifecycle_events": True,
                "provider_failover": False,
            },
            "environment_hints": {
                "deployment_target": "edge",
                "acceleration": "cpu",
                "network_tier": "lan",
                "region": "home",
            },
        }

    def test_validate_capability_manifest_success(self) -> None:
        payload = validate_capability_declaration(self._payload())
        self.assertEqual(payload["manifest_version"], CAPABILITY_DECLARATION_SCHEMA_VERSION)
        self.assertEqual(payload["node"]["node_id"], "node-abc123")
        self.assertEqual(payload["enabled_providers"], ["openai"])
        self.assertEqual(payload["declared_capabilities"], ["task.classification", "task.summarization"])
        self.assertEqual(payload["capability_endpoints"]["task.summarization"]["method"], "POST")
        self.assertEqual(payload["provider_intelligence"][0]["provider"], "openai")
        self.assertEqual(payload["provider_intelligence"][0]["available_models"][0]["model_id"], "gpt-4o-mini")

    def test_rejects_unknown_top_level_keys(self) -> None:
        payload = self._payload()
        payload["unexpected"] = {"x": 1}
        with self.assertRaises(CapabilityManifestValidationError):
            validate_capability_declaration(payload)

    def test_rejects_unsupported_manifest_version(self) -> None:
        payload = self._payload()
        payload["manifest_version"] = "9.9"
        with self.assertRaises(CapabilityManifestValidationError):
            validate_capability_declaration(payload)

    def test_rejects_enabled_provider_not_supported(self) -> None:
        payload = self._payload()
        payload["enabled_providers"] = ["openai", "anthropic"]
        with self.assertRaises(CapabilityManifestValidationError):
            validate_capability_declaration(payload)

    def test_rejects_unknown_nested_keys(self) -> None:
        payload = self._payload()
        payload["environment_hints"]["extra_key"] = "nope"
        with self.assertRaises(CapabilityManifestValidationError):
            validate_capability_declaration(payload)

    def test_rejects_capability_endpoint_for_undeclared_capability(self) -> None:
        payload = self._payload()
        payload["capability_endpoints"]["task.captioning"] = {"transport": "http"}
        with self.assertRaises(CapabilityManifestValidationError):
            validate_capability_declaration(payload)

    def test_rejects_provider_intelligence_outside_supported_providers(self) -> None:
        payload = self._payload()
        payload["provider_intelligence"] = [{"provider": "anthropic", "available_models": []}]
        with self.assertRaises(CapabilityManifestValidationError):
            validate_capability_declaration(payload)


if __name__ == "__main__":
    unittest.main()
