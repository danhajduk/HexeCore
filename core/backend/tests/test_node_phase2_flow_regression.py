import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.system import build_system_router

    FASTAPI_STACK_AVAILABLE = True
except Exception:  # pragma: no cover
    FastAPI = None
    TestClient = None
    build_system_router = None
    FASTAPI_STACK_AVAILABLE = False

from app.api import system as system_api
from app.system.onboarding import NodeOnboardingSessionsStore, NodeRegistrationsStore, NodeTrustIssuanceService, NodeTrustStore
from app.system.onboarding.capability_acceptance import NodeCapabilityAcceptanceService
from app.system.onboarding.capability_profiles import NodeCapabilityProfilesStore
from app.system.onboarding.governance import NodeGovernanceService, NodeGovernanceStore
from app.system.onboarding.governance_status import NodeGovernanceStatusService, NodeGovernanceStatusStore
from app.system.onboarding.node_telemetry import NodeTelemetryService, NodeTelemetryStore


class _FakeRegistry:
    def has_addon(self, addon_id: str) -> bool:
        return False

    def is_platform_managed(self, addon_id: str) -> bool:
        return False

    def set_enabled(self, addon_id: str, enabled: bool) -> None:
        return None

    def is_enabled(self, addon_id: str) -> bool:
        return False

    @property
    def errors(self):
        return []


@unittest.skipIf(not FASTAPI_STACK_AVAILABLE, "fastapi/testclient not available in this environment")
class TestNodePhase2FlowRegression(unittest.TestCase):
    def setUp(self) -> None:
        system_api._RATE_WINDOWS.clear()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.sessions = NodeOnboardingSessionsStore(path=Path(self.tmpdir.name) / "node_onboarding_sessions.json")
        self.registrations = NodeRegistrationsStore(path=Path(self.tmpdir.name) / "node_registrations.json")
        self.trust_store = NodeTrustStore(path=Path(self.tmpdir.name) / "node_trust_records.json")
        self.trust_issuance = NodeTrustIssuanceService(self.trust_store)
        self.capability_profiles = NodeCapabilityProfilesStore(path=Path(self.tmpdir.name) / "node_capability_profiles.json")
        self.capability_acceptance = NodeCapabilityAcceptanceService(self.capability_profiles)
        self.governance_store = NodeGovernanceStore(path=Path(self.tmpdir.name) / "node_governance_bundles.json")
        self.governance_service = NodeGovernanceService(self.governance_store)
        self.governance_status_store = NodeGovernanceStatusStore(path=Path(self.tmpdir.name) / "node_governance_status.json")
        self.governance_status_service = NodeGovernanceStatusService(self.governance_status_store)
        self.telemetry_store = NodeTelemetryStore(path=Path(self.tmpdir.name) / "node_telemetry_events.json")
        self.telemetry_service = NodeTelemetryService(self.telemetry_store)

        app = FastAPI()
        app.include_router(
            build_system_router(
                _FakeRegistry(),
                onboarding_sessions_store=self.sessions,
                node_registrations_store=self.registrations,
                node_trust_issuance=self.trust_issuance,
                node_capability_acceptance=self.capability_acceptance,
                node_governance_service=self.governance_service,
                node_governance_status_service=self.governance_status_service,
                node_telemetry_service=self.telemetry_service,
            ),
            prefix="/api",
        )
        self.client = TestClient(app)
        self.env_patch = patch.dict(
            os.environ,
            {
                "SYNTHIA_AI_NODE_ONBOARDING_ENABLED": "true",
                "SYNTHIA_AI_NODE_ONBOARDING_PROTOCOLS": "1.0",
                "SYNTHIA_NODE_ONBOARDING_SUPPORTED_TYPES": "ai-node,sensor-node",
                "SYNTHIA_ADMIN_TOKEN": "test-token",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.tmpdir.cleanup()

    def _trusted_node(self, nonce: str) -> tuple[str, str]:
        started = self.client.post(
            "/api/system/nodes/onboarding/sessions",
            json={
                "node_name": "phase2-node",
                "node_type": "ai-node",
                "node_software_version": "0.2.0",
                "protocol_version": "1.0",
                "node_nonce": nonce,
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        session_id = started.json()["session"]["session_id"]
        state = started.json()["session"]["approval_url"].split("state=", 1)[1]
        approved = self.client.post(
            f"/api/system/nodes/onboarding/sessions/{session_id}/approve?state={state}",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        node_id = approved.json()["registration"]["node_id"]

        finalized = self.client.get(
            f"/api/system/nodes/onboarding/sessions/{session_id}/finalize?node_nonce={nonce}"
        )
        self.assertEqual(finalized.status_code, 200, finalized.text)

        trust = self.trust_store.get_by_node(node_id)
        self.assertIsNotNone(trust)
        assert trust is not None
        return node_id, trust.node_trust_token

    def _manifest(self, node_id: str) -> dict:
        return {
            "manifest_version": "1.0",
            "node": {
                "node_id": node_id,
                "node_type": "ai-node",
                "node_name": "phase2-node",
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

    def test_valid_declaration_issues_governance_and_persists_profile(self) -> None:
        node_id, token = self._trusted_node("nonce-phase2-1")
        declared = self.client.post(
            "/api/system/nodes/capabilities/declaration",
            json={"manifest": self._manifest(node_id)},
            headers={"X-Node-Trust-Token": token},
        )
        self.assertEqual(declared.status_code, 200, declared.text)
        payload = declared.json()
        self.assertEqual(payload["acceptance_status"], "accepted")
        self.assertTrue(str(payload["capability_profile_id"]).startswith(f"cap-{node_id}-v"))
        self.assertTrue(str(payload["governance_version"]).startswith("gov-v"))

        profiles = self.client.get(
            f"/api/system/nodes/capabilities/profiles?node_id={node_id}",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(profiles.status_code, 200, profiles.text)
        self.assertEqual(len(profiles.json()["items"]), 1)

        governance = self.governance_store.list(node_id=node_id)
        self.assertEqual(len(governance), 1)
        self.assertEqual(governance[0].governance_version, payload["governance_version"])

    def test_invalid_manifest_rejected_without_corrupting_registration(self) -> None:
        node_id, token = self._trusted_node("nonce-phase2-2")
        manifest = self._manifest(node_id)
        manifest["node"]["unknown"] = "bad-key"
        rejected = self.client.post(
            "/api/system/nodes/capabilities/declaration",
            json={"manifest": manifest},
            headers={"X-Node-Trust-Token": token},
        )
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertEqual(rejected.json()["detail"]["error"], "invalid_schema")

        registration = self.registrations.get(node_id)
        self.assertIsNotNone(registration)
        assert registration is not None
        self.assertIsNone(registration.capability_profile_id)
        self.assertEqual(self.governance_store.list(node_id=node_id), [])

    def test_governance_refresh_changed_vs_unchanged(self) -> None:
        node_id, token = self._trusted_node("nonce-phase2-3")
        declared = self.client.post(
            "/api/system/nodes/capabilities/declaration",
            json={"manifest": self._manifest(node_id)},
            headers={"X-Node-Trust-Token": token},
        )
        self.assertEqual(declared.status_code, 200, declared.text)
        version = declared.json()["governance_version"]

        changed = self.client.post(
            "/api/system/nodes/governance/refresh",
            json={"node_id": node_id, "current_governance_version": "gov-v0"},
            headers={"X-Node-Trust-Token": token},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertTrue(bool(changed.json()["updated"]))
        self.assertIn("governance_bundle", changed.json())

        unchanged = self.client.post(
            "/api/system/nodes/governance/refresh",
            json={"node_id": node_id, "current_governance_version": version},
            headers={"X-Node-Trust-Token": token},
        )
        self.assertEqual(unchanged.status_code, 200, unchanged.text)
        self.assertFalse(bool(unchanged.json()["updated"]))

    def test_operational_readiness_evaluation_transitions(self) -> None:
        node_id, token = self._trusted_node("nonce-phase2-4")
        before = self.client.get(
            f"/api/system/nodes/operational-status/{node_id}",
            headers={"X-Node-Trust-Token": token},
        )
        self.assertEqual(before.status_code, 200, before.text)
        self.assertFalse(bool(before.json()["operational_ready"]))
        self.assertEqual(before.json()["capability_status"], "missing")

        declared = self.client.post(
            "/api/system/nodes/capabilities/declaration",
            json={"manifest": self._manifest(node_id)},
            headers={"X-Node-Trust-Token": token},
        )
        self.assertEqual(declared.status_code, 200, declared.text)

        after = self.client.get(
            f"/api/system/nodes/operational-status/{node_id}",
            headers={"X-Node-Trust-Token": token},
        )
        self.assertEqual(after.status_code, 200, after.text)
        self.assertTrue(bool(after.json()["operational_ready"]))
        self.assertEqual(after.json()["capability_status"], "accepted")
        self.assertEqual(after.json()["governance_status"], "issued")


if __name__ == "__main__":
    unittest.main()
