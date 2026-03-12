import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.system.onboarding.capability_acceptance import NodeCapabilityAcceptanceService
from app.system.onboarding.capability_profiles import NodeCapabilityProfilesStore
from app.system.onboarding.provider_model_policy import ProviderModelApprovalPolicyService, ProviderModelPolicyStore


class TestNodeCapabilityAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.profiles = NodeCapabilityProfilesStore(path=Path(self.tmpdir.name) / "profiles.json")
        self.provider_policy_store = ProviderModelPolicyStore(path=Path(self.tmpdir.name) / "provider_policy.json")
        self.provider_policy = ProviderModelApprovalPolicyService(self.provider_policy_store)
        self.service = NodeCapabilityAcceptanceService(self.profiles, provider_model_policy=self.provider_policy)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _manifest(self) -> dict:
        return {
            "manifest_version": "1.0",
            "node": {
                "node_id": "node-abc123",
                "node_type": "ai-node",
                "node_name": "main-ai-node",
                "node_software_version": "0.2.0",
            },
            "declared_task_families": ["task.classification", "task.summarization"],
            "supported_providers": ["openai", "local-llm"],
            "enabled_providers": ["openai"],
            "provider_intelligence": [
                {
                    "provider": "openai",
                    "available_models": [
                        {"model_id": "gpt-4o-mini", "pricing": {"input_per_1k": 0.00015}, "latency_metrics": {"p50_ms": 120.0}}
                    ],
                }
            ],
            "node_features": {"telemetry": True, "governance_refresh": True},
            "environment_hints": {},
        }

    def test_accepts_valid_manifest(self) -> None:
        result = self.service.evaluate(node_id="node-abc123", manifest=self._manifest())
        self.assertTrue(result.accepted)
        self.assertIsNotNone(result.profile)
        assert result.profile is not None
        self.assertTrue(result.profile.profile_id.startswith("cap-node-abc123-v"))
        self.assertEqual(result.profile.provider_intelligence[0]["provider"], "openai")
        self.assertEqual(result.profile.provider_intelligence[0]["available_models"][0]["normalized_model_id"], "gpt-4o-mini")
        self.assertEqual(result.profile.unified_model_descriptors[0]["normalized_model_id"], "gpt-4o-mini")

    def test_normalizes_provider_model_duplicates_into_single_descriptor(self) -> None:
        manifest = self._manifest()
        manifest["provider_intelligence"] = [
            {
                "provider": "OpenAI",
                "available_models": [
                    {"model_id": " GPT-4O-Mini ", "pricing": {"input_per_1k": 0.001}, "latency_metrics": {"p50_ms": 120}},
                    {"model_id": "gpt-4o-mini", "pricing": {"input_per_1k": 0.002}, "latency_metrics": {"p50_ms": 100}},
                ],
            }
        ]
        result = self.service.evaluate(node_id="node-abc123", manifest=manifest)
        self.assertTrue(result.accepted)
        assert result.profile is not None
        models = result.profile.provider_intelligence[0]["available_models"]
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["normalized_model_id"], "gpt-4o-mini")
        self.assertEqual(len(result.profile.unified_model_descriptors), 1)

    def test_rejects_unsupported_task_family(self) -> None:
        manifest = self._manifest()
        manifest["declared_task_families"] = ["task.classification", "task.unknown"]
        with patch.dict(os.environ, {"SYNTHIA_NODE_ALLOWED_TASK_FAMILIES": "task.classification"}, clear=False):
            result = self.service.evaluate(node_id="node-abc123", manifest=manifest)
        self.assertFalse(result.accepted)
        self.assertEqual(result.error_code, "unsupported_task_family")

    def test_rejects_unsupported_provider_identifier(self) -> None:
        manifest = self._manifest()
        manifest["supported_providers"] = ["openai", "provider-x"]
        with patch.dict(os.environ, {"SYNTHIA_NODE_ALLOWED_PROVIDERS": "openai,local-llm"}, clear=False):
            result = self.service.evaluate(node_id="node-abc123", manifest=manifest)
        self.assertFalse(result.accepted)
        self.assertEqual(result.error_code, "unsupported_provider_identifier")

    def test_accepts_provider_identifier_from_node_when_allowlist_not_configured(self) -> None:
        manifest = self._manifest()
        manifest["supported_providers"] = ["provider-x"]
        manifest["enabled_providers"] = ["provider-x"]
        manifest["provider_intelligence"] = [
            {
                "provider": "provider-x",
                "available_models": [{"model_id": "x-large", "pricing": {"input_per_1k": 0.1}}],
            }
        ]
        with patch.dict(os.environ, {"SYNTHIA_NODE_ALLOWED_PROVIDERS": ""}, clear=False):
            result = self.service.evaluate(node_id="node-abc123", manifest=manifest)
        self.assertTrue(result.accepted)

    def test_rejects_unapproved_models_when_provider_policy_exists(self) -> None:
        manifest = self._manifest()
        self.provider_policy.set_allowlist(provider="openai", allowed_models=["gpt-4.1-mini"], updated_by="admin")
        result = self.service.evaluate(node_id="node-abc123", manifest=manifest)
        self.assertFalse(result.accepted)
        self.assertEqual(result.error_code, "provider_model_not_approved")


if __name__ == "__main__":
    unittest.main()
