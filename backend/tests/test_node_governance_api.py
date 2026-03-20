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

from app.system.onboarding import NodeOnboardingSessionsStore, NodeRegistrationsStore, NodeTrustIssuanceService, NodeTrustStore
from app.system.onboarding.capability_acceptance import NodeCapabilityAcceptanceService
from app.system.onboarding.capability_profiles import NodeCapabilityProfilesStore
from app.system.onboarding.governance import NodeGovernanceService, NodeGovernanceStore
from app.system.onboarding.governance_status import NodeGovernanceStatusService, NodeGovernanceStatusStore
from app.system.onboarding.provider_model_policy import ProviderModelApprovalPolicyService, ProviderModelPolicyStore
from app.system.onboarding.node_budgeting import NodeBudgetService, NodeBudgetStore
from app.system.onboarding.model_routing_registry import ModelRoutingRegistryService, ModelRoutingRegistryStore
from app.api import system as system_api


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
class TestNodeGovernanceApi(unittest.TestCase):
    def setUp(self) -> None:
        system_api._RATE_WINDOWS.clear()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.sessions = NodeOnboardingSessionsStore(path=Path(self.tmpdir.name) / "node_onboarding_sessions.json")
        self.registrations = NodeRegistrationsStore(path=Path(self.tmpdir.name) / "node_registrations.json")
        self.trust_store = NodeTrustStore(path=Path(self.tmpdir.name) / "node_trust_records.json")
        self.trust_issuance = NodeTrustIssuanceService(self.trust_store)
        self.capability_profiles = NodeCapabilityProfilesStore(path=Path(self.tmpdir.name) / "node_capability_profiles.json")
        self.provider_policy_store = ProviderModelPolicyStore(path=Path(self.tmpdir.name) / "provider_model_policy.json")
        self.provider_policy = ProviderModelApprovalPolicyService(self.provider_policy_store)
        self.capability_acceptance = NodeCapabilityAcceptanceService(
            self.capability_profiles,
            provider_model_policy=self.provider_policy,
        )
        self.routing_store = ModelRoutingRegistryStore(path=Path(self.tmpdir.name) / "model_routing_registry.json")
        self.routing_service = ModelRoutingRegistryService(self.routing_store)
        self.budget_store = NodeBudgetStore(path=Path(self.tmpdir.name) / "node_budgets.json")
        self.budget_service = NodeBudgetService(self.budget_store, self.routing_service)
        self.governance_store = NodeGovernanceStore(path=Path(self.tmpdir.name) / "node_governance_bundles.json")
        self.governance_service = NodeGovernanceService(
            self.governance_store,
            provider_model_policy=self.provider_policy,
            node_budget_service=self.budget_service,
        )
        self.governance_status_store = NodeGovernanceStatusStore(path=Path(self.tmpdir.name) / "node_governance_status.json")
        self.governance_status_service = NodeGovernanceStatusService(self.governance_status_store)
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
                node_budget_service=self.budget_service,
                provider_model_policy_service=self.provider_policy,
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
                "SYNTHIA_NODE_GOVERNANCE_REFRESH_INTERVAL_S": "180",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.tmpdir.cleanup()

    def _trusted_node(self) -> tuple[str, str]:
        started = self.client.post(
            "/api/system/nodes/onboarding/sessions",
            json={
                "node_name": "main-ai-node",
                "node_type": "ai-node",
                "node_software_version": "0.2.0",
                "protocol_version": "1.0",
                "node_nonce": "nonce-governance-1",
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
            f"/api/system/nodes/onboarding/sessions/{session_id}/finalize?node_nonce=nonce-governance-1"
        )
        self.assertEqual(finalized.status_code, 200, finalized.text)
        self.assertEqual(finalized.json()["onboarding_status"], "approved")

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

    def test_governance_fetch_requires_capability_declaration(self) -> None:
        node_id, trust_token = self._trusted_node()
        res = self.client.get(
            f"/api/system/nodes/governance/current?node_id={node_id}",
            headers={"X-Node-Trust-Token": trust_token},
        )
        self.assertEqual(res.status_code, 409, res.text)
        self.assertEqual(res.json()["detail"]["error"], "capability_declaration_required")

    def test_governance_fetch_returns_current_bundle(self) -> None:
        node_id, trust_token = self._trusted_node()
        declared = self.client.post(
            "/api/system/nodes/capabilities/declaration",
            json={"manifest": self._manifest(node_id)},
            headers={"X-Node-Trust-Token": trust_token},
        )
        self.assertEqual(declared.status_code, 200, declared.text)
        profile_id = declared.json()["capability_profile_id"]
        governance_version = declared.json()["governance_version"]

        res = self.client.get(
            f"/api/system/nodes/governance/current?node_id={node_id}",
            headers={"X-Node-Trust-Token": trust_token},
        )
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()
        self.assertEqual(payload["node_id"], node_id)
        self.assertEqual(payload["capability_profile_id"], profile_id)
        self.assertEqual(payload["governance_version"], governance_version)
        self.assertEqual(payload["refresh_interval_s"], 180)
        self.assertEqual(payload["governance_bundle"]["governance_version"], governance_version)
        self.assertEqual(payload["governance_bundle"]["capability_profile_id"], profile_id)
        self.assertIn("private, max-age=", res.headers.get("cache-control", ""))

        status = self.governance_status_store.get(node_id)
        self.assertIsNotNone(status)
        assert status is not None
        self.assertEqual(status.active_governance_version, governance_version)
        self.assertTrue(str(status.last_issued_timestamp or "").strip())
        self.assertTrue(str(status.last_refresh_request_timestamp or "").strip())

        registry = self.client.get("/api/system/nodes/registry", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(registry.status_code, 200, registry.text)
        items = registry.json()["items"]
        self.assertEqual(len(items), 1)
        node = items[0]
        self.assertEqual(node["node_id"], node_id)
        self.assertEqual(node["capability_status"], "accepted")
        self.assertEqual(node["governance_sync_status"], "issued")
        self.assertTrue(bool(node["operational_ready"]))
        self.assertEqual(node["active_governance_version"], governance_version)

    def test_governance_bundle_includes_budget_policy_and_routing_constraints(self) -> None:
        node_id, trust_token = self._trusted_node()
        self.provider_policy.set_allowlist(provider="openai", allowed_models=["gpt-4o-mini"], updated_by="test")
        declared = self.client.post(
            "/api/system/nodes/capabilities/declaration",
            json={"manifest": self._manifest(node_id)},
            headers={"X-Node-Trust-Token": trust_token},
        )
        self.assertEqual(declared.status_code, 200, declared.text)

        budget_declared = self.client.post(
            "/api/system/nodes/budgets/declaration",
            headers={"X-Node-Trust-Token": trust_token},
            json={"node_id": node_id, "compute_unit": "tokens"},
        )
        self.assertEqual(budget_declared.status_code, 200, budget_declared.text)
        configured = self.client.put(
            f"/api/system/nodes/budgets/{node_id}",
            headers={"X-Admin-Token": "test-token"},
            json={"node_budget": {"node_money_limit": 10.0, "node_compute_limit": 5000.0, "compute_unit": "tokens"}},
        )
        self.assertEqual(configured.status_code, 200, configured.text)

        res = self.client.get(
            f"/api/system/nodes/governance/current?node_id={node_id}",
            headers={"X-Node-Trust-Token": trust_token},
        )
        self.assertEqual(res.status_code, 200, res.text)
        bundle = res.json()["governance_bundle"]
        self.assertIn("routing_policy_constraints", bundle)
        self.assertEqual(bundle["routing_policy_constraints"]["allowed_providers"], ["openai"])
        self.assertEqual(bundle["routing_policy_constraints"]["allowed_task_families"], ["task.classification", "task.summarization"])
        self.assertEqual(bundle["routing_policy_constraints"]["allowed_models"]["openai"], ["gpt-4o-mini"])
        self.assertIn("budget_policy", bundle)
        self.assertEqual(bundle["budget_policy"]["status"], "active")
        self.assertEqual(bundle["budget_policy"]["service"], "ai.inference")
        self.assertTrue(bundle["budget_policy"]["budget_policy_version"].startswith("nbp-"))
        self.assertGreaterEqual(len(bundle["budget_policy"]["grants"]), 1)

    def test_governance_refresh_returns_updated_bundle_when_version_changes(self) -> None:
        node_id, trust_token = self._trusted_node()
        declared = self.client.post(
            "/api/system/nodes/capabilities/declaration",
            json={"manifest": self._manifest(node_id)},
            headers={"X-Node-Trust-Token": trust_token},
        )
        self.assertEqual(declared.status_code, 200, declared.text)
        governance_version = declared.json()["governance_version"]

        refreshed = self.client.post(
            "/api/system/nodes/governance/refresh",
            json={"node_id": node_id, "current_governance_version": "gov-v0"},
            headers={"X-Node-Trust-Token": trust_token},
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        payload = refreshed.json()
        self.assertTrue(bool(payload["updated"]))
        self.assertEqual(payload["governance_version"], governance_version)
        self.assertIn("governance_bundle", payload)
        self.assertIn("private, max-age=5", refreshed.headers.get("cache-control", ""))

    def test_governance_refresh_returns_not_updated_when_version_matches(self) -> None:
        node_id, trust_token = self._trusted_node()
        declared = self.client.post(
            "/api/system/nodes/capabilities/declaration",
            json={"manifest": self._manifest(node_id)},
            headers={"X-Node-Trust-Token": trust_token},
        )
        self.assertEqual(declared.status_code, 200, declared.text)
        governance_version = declared.json()["governance_version"]

        refreshed = self.client.post(
            "/api/system/nodes/governance/refresh",
            json={"node_id": node_id, "current_governance_version": governance_version},
            headers={"X-Node-Trust-Token": trust_token},
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        payload = refreshed.json()
        self.assertFalse(bool(payload["updated"]))
        self.assertEqual(payload["governance_version"], governance_version)
        self.assertNotIn("governance_bundle", payload)


if __name__ == "__main__":
    unittest.main()
