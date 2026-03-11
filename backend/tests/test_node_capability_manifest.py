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
            "supported_providers": ["openai", "local-llm"],
            "enabled_providers": ["openai"],
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


if __name__ == "__main__":
    unittest.main()
