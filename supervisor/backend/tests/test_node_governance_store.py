import tempfile
import unittest
from pathlib import Path

from app.system.onboarding.capability_profiles import NodeCapabilityProfileRecord
from app.system.onboarding.governance import NodeGovernanceService, NodeGovernanceStore


class TestNodeGovernanceStore(unittest.TestCase):
    def test_issue_baseline_is_idempotent_for_same_profile_and_versions_for_new_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = NodeGovernanceStore(path=Path(tmpdir) / "node_governance_bundles.json")
            service = NodeGovernanceService(store)

            profile_v1 = NodeCapabilityProfileRecord(
                profile_id="cap-node-a-v1",
                node_id="node-a",
                declared_task_families=["task.classification"],
                enabled_providers=["openai"],
                feature_flags={
                    "telemetry": True,
                    "lifecycle_events": True,
                    "provider_failover": False,
                    "governance_refresh": True,
                },
                acceptance_timestamp="2026-03-11T00:00:00+00:00",
                manifest_version="1.0",
                declaration_digest="digest-v1",
                declaration_raw={},
            )
            first = service.issue_baseline_for_profile(node_id="node-a", node_type="ai", profile=profile_v1)
            self.assertEqual(first.governance_version, "gov-v1")
            self.assertEqual(first.capability_profile_id, "cap-node-a-v1")
            self.assertTrue(first.feature_gating_defaults["allow_governance_refresh"])
            self.assertTrue(first.telemetry_requirements["required"])

            same = service.issue_baseline_for_profile(node_id="node-a", node_type="ai", profile=profile_v1)
            self.assertEqual(same.governance_version, "gov-v1")
            self.assertEqual(len(store.list(node_id="node-a")), 1)

            profile_v2 = NodeCapabilityProfileRecord(
                profile_id="cap-node-a-v2",
                node_id="node-a",
                declared_task_families=["task.classification", "task.summarization"],
                enabled_providers=["openai", "local-llm"],
                feature_flags={
                    "telemetry": True,
                    "lifecycle_events": False,
                    "provider_failover": True,
                    "governance_refresh": True,
                },
                acceptance_timestamp="2026-03-11T00:01:00+00:00",
                manifest_version="1.0",
                declaration_digest="digest-v2",
                declaration_raw={},
            )
            second = service.issue_baseline_for_profile(node_id="node-a", node_type="ai", profile=profile_v2)
            self.assertEqual(second.governance_version, "gov-v2")
            self.assertEqual(second.capability_profile_id, "cap-node-a-v2")
            self.assertTrue(second.feature_gating_defaults["allow_provider_failover"])
            self.assertEqual(len(store.list(node_id="node-a")), 2)


if __name__ == "__main__":
    unittest.main()
