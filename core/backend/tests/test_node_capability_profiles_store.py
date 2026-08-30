import json
import tempfile
import unittest
from pathlib import Path

from app.system.onboarding.capability_profiles import NodeCapabilityProfilesStore


class TestNodeCapabilityProfilesStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "node_capability_profiles.json"
        self.store = NodeCapabilityProfilesStore(path=self.path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _manifest(self, providers: list[str] | None = None) -> dict:
        return {
            "manifest_version": "1.0",
            "node": {"node_id": "node-abc123", "node_type": "ai-node", "node_name": "n1", "node_software_version": "0.2.0"},
            "declared_task_families": ["task.classification"],
            "supported_providers": ["openai", "local-llm"],
            "enabled_providers": list(providers or ["openai"]),
            "provider_intelligence": [
                {
                    "provider": "openai",
                    "available_models": [
                        {"model_id": "gpt-4o-mini", "pricing": {"input_per_1k": 0.00015}, "latency_metrics": {"p50_ms": 120.0}}
                    ],
                }
            ],
            "node_features": {"telemetry": True},
            "environment_hints": {},
        }

    def test_create_or_get_reuses_profile_for_same_manifest(self) -> None:
        profile1 = self.store.create_or_get(
            node_id="node-abc123",
            manifest=self._manifest(),
            declared_task_families=["task.classification"],
            requested_task_families=["task.chat"],
            enabled_providers=["openai"],
            feature_flags={"telemetry": True},
            manifest_version="1.0",
            provider_intelligence=self._manifest()["provider_intelligence"],
        )
        profile2 = self.store.create_or_get(
            node_id="node-abc123",
            manifest=self._manifest(),
            declared_task_families=["task.classification"],
            requested_task_families=["task.chat"],
            enabled_providers=["openai"],
            feature_flags={"telemetry": True},
            manifest_version="1.0",
            provider_intelligence=self._manifest()["provider_intelligence"],
        )
        self.assertEqual(profile1.profile_id, profile2.profile_id)
        self.assertEqual(profile1.provided_task_families, ["task.classification"])
        self.assertEqual(profile1.requested_task_families, ["task.chat"])
        self.assertEqual(profile1.to_dict()["provided_task_families"], ["task.classification"])
        self.assertEqual(profile1.to_dict()["requested_task_families"], ["task.chat"])
        self.assertEqual(profile1.provider_intelligence[0]["provider"], "openai")
        self.assertEqual(profile1.to_dict()["capability_taxonomy"]["activation"]["stage"], "profile_accepted")
        self.assertEqual(len(self.store.list(node_id="node-abc123")), 1)

    def test_create_or_get_versions_profiles_on_manifest_change(self) -> None:
        p1 = self.store.create_or_get(
            node_id="node-abc123",
            manifest=self._manifest(["openai"]),
            declared_task_families=["task.classification"],
            requested_task_families=["task.chat"],
            enabled_providers=["openai"],
            feature_flags={"telemetry": True},
            manifest_version="1.0",
            provider_intelligence=self._manifest(["openai"])["provider_intelligence"],
        )
        p2 = self.store.create_or_get(
            node_id="node-abc123",
            manifest=self._manifest(["local-llm"]),
            declared_task_families=["task.classification"],
            requested_task_families=["task.reasoning"],
            enabled_providers=["local-llm"],
            feature_flags={"telemetry": True},
            manifest_version="1.0",
            provider_intelligence=[
                {
                    "provider": "local-llm",
                    "available_models": [
                        {"model_id": "llama3", "pricing": {"input_per_1k": 0.0}, "latency_metrics": {"p50_ms": 95.0}}
                    ],
                }
            ],
        )
        self.assertNotEqual(p1.profile_id, p2.profile_id)
        self.assertTrue(p1.profile_id.endswith("-v1"))
        self.assertTrue(p2.profile_id.endswith("-v2"))
        self.assertEqual(self.store.latest_for_node("node-abc123").profile_id, p2.profile_id)  # type: ignore[union-attr]

    def test_legacy_profile_load_backfills_provider_families_and_empty_requests(self) -> None:
        payload = {
            "schema_version": "1",
            "items": [
                {
                    "profile_id": "cap-node-legacy-v1",
                    "node_id": "node-legacy",
                    "declared_capabilities": [" task.chat ", ""],
                    "enabled_providers": ["openai"],
                    "feature_flags": {"telemetry": True},
                    "acceptance_timestamp": "2026-03-11T00:00:00+00:00",
                    "manifest_version": "1.0",
                    "declaration_digest": "digest-legacy",
                    "declaration_raw": {},
                }
            ],
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")

        reloaded = NodeCapabilityProfilesStore(path=self.path)
        profile = reloaded.get("cap-node-legacy-v1")

        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertEqual(profile.declared_task_families, ["task.chat"])
        self.assertEqual(profile.provided_task_families, ["task.chat"])
        self.assertEqual(profile.requested_task_families, [])
        self.assertEqual(profile.to_dict()["provided_task_families"], ["task.chat"])
        self.assertEqual(profile.to_dict()["requested_task_families"], [])

    def test_requester_only_profile_load_preserves_empty_provider_families(self) -> None:
        payload = {
            "schema_version": "1",
            "items": [
                {
                    "profile_id": "cap-node-voice-v1",
                    "node_id": "node-voice",
                    "declared_task_families": [],
                    "provided_task_families": [],
                    "requested_task_families": ["task.chat"],
                    "enabled_providers": [],
                    "feature_flags": {},
                    "acceptance_timestamp": "2026-03-11T00:00:00+00:00",
                    "manifest_version": "1.0",
                    "declaration_digest": "digest-requester",
                    "declaration_raw": {},
                }
            ],
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")

        reloaded = NodeCapabilityProfilesStore(path=self.path)
        profile = reloaded.get("cap-node-voice-v1")

        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertEqual(profile.declared_task_families, [])
        self.assertEqual(profile.provided_task_families, [])
        self.assertEqual(profile.requested_task_families, ["task.chat"])


if __name__ == "__main__":
    unittest.main()
