import os
import tempfile
import unittest
import json
from datetime import datetime, timedelta, timezone
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

from app.system.onboarding import (
    ModelRoutingRegistryService,
    ModelRoutingRegistryStore,
    NodeBudgetService,
    NodeBudgetStore,
    NodeOnboardingSessionsStore,
    NodeRegistrationsStore,
    NodeTrustIssuanceService,
    NodeTrustStore,
)
from app.system.onboarding.capability_acceptance import NodeCapabilityAcceptanceService
from app.system.onboarding.capability_profiles import NodeCapabilityProfilesStore
from app.system.onboarding.governance import NodeGovernanceService, NodeGovernanceStore
from app.system.onboarding.governance_status import NodeGovernanceStatusService, NodeGovernanceStatusStore
from app.api import system as system_api
from app.system.audit import AuditLogStore


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


class _FakeMqttManager:
    def __init__(self) -> None:
        self.published: list[dict[str, object]] = []

    async def publish(self, topic: str, payload: dict, retain: bool = True, qos: int = 1):
        self.published.append({"topic": topic, "payload": payload, "retain": retain, "qos": qos})
        return {"ok": True, "topic": topic, "rc": 0}


@unittest.skipIf(not FASTAPI_STACK_AVAILABLE, "fastapi/testclient not available in this environment")
class TestNodeBudgetApi(unittest.TestCase):
    def setUp(self) -> None:
        system_api._RATE_WINDOWS.clear()
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self.sessions = NodeOnboardingSessionsStore(path=base / "node_onboarding_sessions.json")
        self.registrations = NodeRegistrationsStore(path=base / "node_registrations.json")
        self.trust_store = NodeTrustStore(path=base / "node_trust_records.json")
        self.trust_issuance = NodeTrustIssuanceService(self.trust_store)
        self.budget_store = NodeBudgetStore(path=base / "node_budgets.json")
        self.routing_store = ModelRoutingRegistryStore(path=base / "model_routing_registry.json")
        self.routing_service = ModelRoutingRegistryService(self.routing_store)
        self.budget_service = NodeBudgetService(self.budget_store, self.routing_service)
        self.capability_profiles = NodeCapabilityProfilesStore(path=base / "node_capability_profiles.json")
        self.capability_acceptance = NodeCapabilityAcceptanceService(self.capability_profiles)
        self.governance_store = NodeGovernanceStore(path=base / "node_governance_bundles.json")
        self.governance_service = NodeGovernanceService(
            self.governance_store,
            node_budget_service=self.budget_service,
        )
        self.governance_status_store = NodeGovernanceStatusStore(path=base / "node_governance_status.json")
        self.governance_status_service = NodeGovernanceStatusService(self.governance_status_store)
        self.audit_store = AuditLogStore(str(base / "audit.log"))
        self.audit_path = base / "audit.log"
        self.mqtt = _FakeMqttManager()

        app = FastAPI()
        app.include_router(
            build_system_router(
                _FakeRegistry(),
                mqtt_manager=self.mqtt,
                onboarding_sessions_store=self.sessions,
                node_registrations_store=self.registrations,
                node_trust_issuance=self.trust_issuance,
                node_budget_service=self.budget_service,
                node_capability_acceptance=self.capability_acceptance,
                node_governance_service=self.governance_service,
                node_governance_status_service=self.governance_status_service,
                audit_store=self.audit_store,
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

    def _trusted_node(self) -> tuple[str, str]:
        started = self.client.post(
            "/api/system/nodes/onboarding/sessions",
            json={
                "node_name": "budget-node",
                "node_type": "ai-node",
                "node_software_version": "0.3.0",
                "protocol_version": "1.0",
                "node_nonce": "nonce-budget-1",
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
            f"/api/system/nodes/onboarding/sessions/{session_id}/finalize?node_nonce=nonce-budget-1"
        )
        self.assertEqual(finalized.status_code, 200, finalized.text)
        trust = self.trust_store.get_by_node(node_id)
        self.assertIsNotNone(trust)
        assert trust is not None
        return node_id, trust.node_trust_token

    def _audit_events(self) -> list[dict]:
        if not self.audit_path.exists():
            return []
        return [json.loads(line) for line in self.audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _declare_capabilities(self, node_id: str, trust_token: str) -> None:
        declared = self.client.post(
            "/api/system/nodes/capabilities/declaration",
            headers={"X-Node-Trust-Token": trust_token},
            json={
                "manifest": {
                    "manifest_version": "1.0",
                    "node": {
                        "node_id": node_id,
                        "node_type": "ai-node",
                        "node_name": "budget-node",
                        "node_software_version": "0.3.0",
                    },
                    "declared_task_families": ["task.summarization"],
                    "supported_providers": ["openai"],
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
            },
        )
        self.assertEqual(declared.status_code, 200, declared.text)

    def test_trusted_node_can_declare_budget_capabilities(self) -> None:
        node_id, trust_token = self._trusted_node()
        res = self.client.post(
            "/api/system/nodes/budgets/declaration",
            headers={"X-Node-Trust-Token": trust_token},
            json={
                "node_id": node_id,
                "currency": "USD",
                "compute_unit": "cost_units",
                "default_period": "monthly",
                "supports_money_budget": True,
                "supports_compute_budget": True,
                "supports_customer_allocations": True,
                "supports_provider_allocations": True,
                "supported_providers": ["openai", "local-llm"],
                "setup_requirements": ["operator_budget_confirmation"],
                "suggested_money_limit": 10.0,
                "suggested_compute_limit": 100.0,
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        payload = res.json()["declaration"]
        self.assertEqual(payload["node_id"], node_id)
        self.assertTrue(payload["supports_provider_allocations"])
        self.assertEqual(payload["supported_providers"], ["local-llm", "openai"])

    def test_admin_can_configure_node_budget_bundle(self) -> None:
        node_id, trust_token = self._trusted_node()
        self._declare_capabilities(node_id, trust_token)
        declared = self.client.post(
            "/api/system/nodes/budgets/declaration",
            headers={"X-Node-Trust-Token": trust_token},
            json={
                "node_id": node_id,
                "supports_provider_allocations": True,
                "supported_providers": ["openai"],
                "suggested_money_limit": 10.0,
                "suggested_compute_limit": 100.0,
            },
        )
        self.assertEqual(declared.status_code, 200, declared.text)

        configured = self.client.put(
            f"/api/system/nodes/budgets/{node_id}",
            headers={"X-Admin-Token": "test-token"},
            json={
                "node_budget": {
                    "currency": "USD",
                    "compute_unit": "cost_units",
                    "period": "monthly",
                    "reset_policy": "calendar",
                    "enforcement_mode": "hard_stop",
                    "overcommit_enabled": False,
                    "node_money_limit": 10.0,
                    "node_compute_limit": 100.0,
                },
                "customer_allocations": [
                    {"subject_id": "cust-a", "money_limit": 3.3, "compute_limit": 30},
                    {"subject_id": "cust-b", "money_limit": 3.3, "compute_limit": 30},
                    {"subject_id": "cust-c", "money_limit": 3.3, "compute_limit": 30},
                ],
                "provider_allocations": [
                    {"subject_id": "openai", "money_limit": 8.0, "compute_limit": 80},
                ],
            },
        )
        self.assertEqual(configured.status_code, 200, configured.text)
        budget = configured.json()["budget"]
        self.assertEqual(budget["setup_status"], "configured")
        self.assertEqual(len(budget["customer_allocations"]), 3)
        self.assertEqual(len(budget["provider_allocations"]), 1)

        listed = self.client.get("/api/system/nodes/budgets", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["items"][0]["node_id"], node_id)

    def test_outdated_node_budget_policy_is_blocked_until_governance_refresh(self) -> None:
        node_id, trust_token = self._trusted_node()
        self._declare_capabilities(node_id, trust_token)
        declared = self.client.post(
            "/api/system/nodes/budgets/declaration",
            headers={"X-Node-Trust-Token": trust_token},
            json={"node_id": node_id, "compute_unit": "tokens"},
        )
        self.assertEqual(declared.status_code, 200, declared.text)
        configured = self.client.put(
            f"/api/system/nodes/budgets/{node_id}",
            headers={"X-Admin-Token": "test-token"},
            json={"node_budget": {"node_money_limit": 10.0, "node_compute_limit": 10000.0, "compute_unit": "tokens"}},
        )
        self.assertEqual(configured.status_code, 200, configured.text)

        status = self.governance_status_store.get(node_id)
        self.assertIsNotNone(status)
        assert status is not None
        outdated_at = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        self.governance_status_store.upsert(
            node_id=node_id,
            active_governance_version=status.active_governance_version,
            last_issued_timestamp=status.last_issued_timestamp,
            last_refresh_request_timestamp=outdated_at,
        )

        blocked = self.client.get(
            f"/api/system/nodes/budgets/policy/current?node_id={node_id}",
            headers={"X-Node-Trust-Token": trust_token},
        )
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(blocked.json()["detail"]["error"], "node_governance_outdated")

        refresh = self.client.post(
            "/api/system/nodes/governance/refresh",
            headers={"X-Node-Trust-Token": trust_token},
            json={"node_id": node_id},
        )
        self.assertEqual(refresh.status_code, 200, refresh.text)

        policy = self.client.get(
            f"/api/system/nodes/budgets/policy/current?node_id={node_id}",
            headers={"X-Node-Trust-Token": trust_token},
        )
        self.assertEqual(policy.status_code, 200, policy.text)
        self.assertEqual(policy.json()["budget_policy"]["status"], "active")

        freshness_events = [event for event in self._audit_events() if event.get("event_type") == "node_governance_freshness_changed"]
        self.assertTrue(freshness_events)
        self.assertEqual(freshness_events[-1]["details"]["freshness_state"], "fresh")

    def test_rejects_customer_budget_sum_above_node_total_without_overcommit(self) -> None:
        node_id, trust_token = self._trusted_node()
        declared = self.client.post(
            "/api/system/nodes/budgets/declaration",
            headers={"X-Node-Trust-Token": trust_token},
            json={"node_id": node_id},
        )
        self.assertEqual(declared.status_code, 200, declared.text)

        configured = self.client.put(
            f"/api/system/nodes/budgets/{node_id}",
            headers={"X-Admin-Token": "test-token"},
            json={
                "node_budget": {
                    "node_money_limit": 10.0,
                    "node_compute_limit": 100.0,
                },
                "customer_allocations": [
                    {"subject_id": "cust-a", "money_limit": 6.0, "compute_limit": 30},
                    {"subject_id": "cust-b", "money_limit": 5.0, "compute_limit": 30},
                ],
            },
        )
        self.assertEqual(configured.status_code, 400, configured.text)
        self.assertEqual(configured.json()["detail"]["error"], "customer_budget_allocations_exceed_node_money_limit")

    def test_rejects_provider_allocation_for_unsupported_provider(self) -> None:
        node_id, trust_token = self._trusted_node()
        declared = self.client.post(
            "/api/system/nodes/budgets/declaration",
            headers={"X-Node-Trust-Token": trust_token},
            json={
                "node_id": node_id,
                "supports_provider_allocations": True,
                "supported_providers": ["openai"],
            },
        )
        self.assertEqual(declared.status_code, 200, declared.text)

        configured = self.client.put(
            f"/api/system/nodes/budgets/{node_id}",
            headers={"X-Admin-Token": "test-token"},
            json={
                "node_budget": {"node_money_limit": 10.0, "node_compute_limit": 100.0},
                "provider_allocations": [{"subject_id": "anthropic", "money_limit": 5.0, "compute_limit": 50}],
            },
        )
        self.assertEqual(configured.status_code, 400, configured.text)
        self.assertEqual(configured.json()["detail"]["error"], "provider_budget_subject_not_supported")

    def test_trusted_node_can_report_actual_budget_usage(self) -> None:
        node_id, trust_token = self._trusted_node()
        declared = self.client.post(
            "/api/system/nodes/budgets/declaration",
            headers={"X-Node-Trust-Token": trust_token},
            json={"node_id": node_id},
        )
        self.assertEqual(declared.status_code, 200, declared.text)
        configured = self.client.put(
            f"/api/system/nodes/budgets/{node_id}",
            headers={"X-Admin-Token": "test-token"},
            json={"node_budget": {"node_money_limit": 10.0, "node_compute_limit": 100.0}},
        )
        self.assertEqual(configured.status_code, 200, configured.text)

        reservation = self.budget_service.reserve_scheduler_budget(
            job_id="job-usage-1",
            addon_id="vision",
            cost_units=6,
            payload={"budget_scope": {"node_id": node_id, "money_estimate": 2.0}},
            constraints={},
        )
        self.assertIsNotNone(reservation)

        reported = self.client.post(
            "/api/system/nodes/budgets/usage-report",
            headers={"X-Node-Trust-Token": trust_token},
            json={
                "node_id": node_id,
                "job_id": "job-usage-1",
                "status": "completed",
                "actual_money_spend": 1.5,
                "actual_compute_spend": 4.0,
            },
        )
        self.assertEqual(reported.status_code, 200, reported.text)
        payload = reported.json()
        self.assertEqual(payload["reservation"]["state"], "finalized")
        self.assertEqual(payload["reservation"]["money_actual"], 1.5)
        self.assertEqual(payload["budget"]["usage_summary"]["node"]["actual_money"], 1.5)

    def test_trusted_node_can_poll_budget_policy_and_report_periodic_usage_summary(self) -> None:
        node_id, trust_token = self._trusted_node()
        declared = self.client.post(
            "/api/system/nodes/budgets/declaration",
            headers={"X-Node-Trust-Token": trust_token},
            json={"node_id": node_id, "compute_unit": "tokens"},
        )
        self.assertEqual(declared.status_code, 200, declared.text)
        configured = self.client.put(
            f"/api/system/nodes/budgets/{node_id}",
            headers={"X-Admin-Token": "test-token"},
            json={"node_budget": {"node_money_limit": 12.0, "node_compute_limit": 9000.0, "compute_unit": "tokens"}},
        )
        self.assertEqual(configured.status_code, 200, configured.text)

        current = self.client.get(
            f"/api/system/nodes/budgets/policy/current?node_id={node_id}",
            headers={"X-Node-Trust-Token": trust_token},
        )
        self.assertEqual(current.status_code, 200, current.text)
        policy = current.json()["budget_policy"]
        self.assertEqual(policy["status"], "active")
        self.assertTrue(policy["budget_policy_version"].startswith("nbp-"))
        self.assertGreaterEqual(len(policy["grants"]), 1)

        refreshed = self.client.post(
            "/api/system/nodes/budgets/policy/refresh",
            headers={"X-Node-Trust-Token": trust_token},
            json={
                "node_id": node_id,
                "current_budget_policy_version": policy["budget_policy_version"],
                "current_governance_version": current.json()["governance_version"],
            },
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertFalse(bool(refreshed.json()["updated"]))

        report = self.client.post(
            "/api/system/nodes/budgets/usage-summary",
            headers={"X-Node-Trust-Token": trust_token},
            json={
                "node_id": node_id,
                "service": "ai.inference",
                "grant_id": policy["grants"][0]["grant_id"],
                "period_start": policy["period_start"],
                "period_end": policy["period_end"],
                "used_requests": 143,
                "used_tokens": 284231,
                "used_cost_cents": 731,
                "denials": 3,
                "error_counts": {"provider_unavailable": 1, "budget_exceeded": 2},
            },
        )
        self.assertEqual(report.status_code, 200, report.text)
        self.assertEqual(report.json()["report"]["used_tokens"], 284231)

        listed = self.client.get(
            f"/api/system/nodes/budgets/{node_id}/usage-reports",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["items"][0]["used_cost_cents"], 731)
        self.assertEqual(listed.json()["items"][0]["error_counts"]["budget_exceeded"], 2)

    def test_budget_changes_publish_grants_and_budget_delete_publishes_revocations(self) -> None:
        node_id, trust_token = self._trusted_node()
        declared = self.client.post(
            "/api/system/nodes/budgets/declaration",
            headers={"X-Node-Trust-Token": trust_token},
            json={"node_id": node_id},
        )
        self.assertEqual(declared.status_code, 200, declared.text)
        configured = self.client.put(
            f"/api/system/nodes/budgets/{node_id}",
            headers={"X-Admin-Token": "test-token"},
            json={"node_budget": {"node_money_limit": 10.0, "node_compute_limit": 100.0}},
        )
        self.assertEqual(configured.status_code, 200, configured.text)
        self.assertTrue(any(row["topic"] == f"synthia/policy/grants/{node_id}" for row in self.mqtt.published))
        published_grant = next(row for row in self.mqtt.published if row["topic"] == f"synthia/policy/grants/{node_id}")
        self.assertEqual(published_grant["payload"]["service"], "ai.inference")

        deleted = self.client.delete(
            f"/api/system/nodes/budgets/{node_id}",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        published_topics = [row["topic"] for row in self.mqtt.published]
        self.assertIn(f"synthia/policy/revocations/{node_id}", published_topics)

    def test_admin_can_manage_customer_and_provider_allocations_and_usage_view(self) -> None:
        node_id, trust_token = self._trusted_node()
        declared = self.client.post(
            "/api/system/nodes/budgets/declaration",
            headers={"X-Node-Trust-Token": trust_token},
            json={
                "node_id": node_id,
                "supports_provider_allocations": True,
                "supported_providers": ["openai"],
            },
        )
        self.assertEqual(declared.status_code, 200, declared.text)
        configured = self.client.put(
            f"/api/system/nodes/budgets/{node_id}",
            headers={"X-Admin-Token": "test-token"},
            json={"node_budget": {"node_money_limit": 10.0, "node_compute_limit": 100.0}},
        )
        self.assertEqual(configured.status_code, 200, configured.text)

        customer = self.client.put(
            f"/api/system/nodes/budgets/{node_id}/customers/cust-x",
            headers={"X-Admin-Token": "test-token"},
            json={"subject_id": "ignored", "money_limit": 4.0, "compute_limit": 40.0},
        )
        self.assertEqual(customer.status_code, 200, customer.text)
        self.assertEqual(customer.json()["allocation"]["subject_id"], "cust-x")

        provider = self.client.put(
            f"/api/system/nodes/budgets/{node_id}/providers/openai",
            headers={"X-Admin-Token": "test-token"},
            json={"subject_id": "ignored", "money_limit": 7.0, "compute_limit": 70.0},
        )
        self.assertEqual(provider.status_code, 200, provider.text)
        self.assertEqual(provider.json()["allocation"]["subject_id"], "openai")

        reservation = self.budget_service.reserve_scheduler_budget(
            job_id="job-usage-2",
            addon_id="vision",
            cost_units=5,
            payload={"budget_scope": {"node_id": node_id, "customer_id": "cust-x", "provider": "openai", "money_estimate": 2.0}},
            constraints={},
        )
        self.assertIsNotNone(reservation)

        usage = self.client.get(
            f"/api/system/nodes/budgets/{node_id}/usage",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(usage.status_code, 200, usage.text)
        usage_payload = usage.json()["usage"]
        self.assertEqual(usage_payload["usage_summary"]["node"]["reserved_money"], 2.0)
        self.assertIsNotNone(usage_payload["next_reset_at"])
        self.assertEqual(len(usage_payload["reservations"]), 1)

        deleted_customer = self.client.delete(
            f"/api/system/nodes/budgets/{node_id}/customers/cust-x",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(deleted_customer.status_code, 200, deleted_customer.text)

        deleted_provider = self.client.delete(
            f"/api/system/nodes/budgets/{node_id}/providers/openai",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(deleted_provider.status_code, 200, deleted_provider.text)

        deleted_budget = self.client.delete(
            f"/api/system/nodes/budgets/{node_id}",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(deleted_budget.status_code, 200, deleted_budget.text)
        self.assertEqual(deleted_budget.json()["budget"]["setup_status"], "needs_configuration")

        event_types = [item["event_type"] for item in self._audit_events()]
        self.assertIn("node_budget_customer_allocation_upserted", event_types)
        self.assertIn("node_budget_provider_allocation_upserted", event_types)
        self.assertIn("node_budget_deleted", event_types)

    def test_admin_can_top_up_override_force_release_and_reset_budget(self) -> None:
        node_id, trust_token = self._trusted_node()
        declared = self.client.post(
            "/api/system/nodes/budgets/declaration",
            headers={"X-Node-Trust-Token": trust_token},
            json={"node_id": node_id},
        )
        self.assertEqual(declared.status_code, 200, declared.text)
        configured = self.client.put(
            f"/api/system/nodes/budgets/{node_id}",
            headers={"X-Admin-Token": "test-token"},
            json={"node_budget": {"node_money_limit": 10.0, "node_compute_limit": 100.0}},
        )
        self.assertEqual(configured.status_code, 200, configured.text)

        top_up = self.client.post(
            f"/api/system/nodes/budgets/{node_id}/top-up",
            headers={"X-Admin-Token": "test-token"},
            json={"money_delta": 2.0, "compute_delta": 25.0},
        )
        self.assertEqual(top_up.status_code, 200, top_up.text)
        self.assertEqual(top_up.json()["budget"]["node_budget"]["node_money_limit"], 12.0)
        self.assertEqual(top_up.json()["budget"]["node_budget"]["node_compute_limit"], 125.0)

        override = self.client.post(
            f"/api/system/nodes/budgets/{node_id}/override",
            headers={"X-Admin-Token": "test-token"},
            json={"enforcement_mode": "warn", "overcommit_enabled": True},
        )
        self.assertEqual(override.status_code, 200, override.text)
        self.assertEqual(override.json()["budget"]["node_budget"]["enforcement_mode"], "warn")
        self.assertTrue(override.json()["budget"]["node_budget"]["overcommit_enabled"])

        self.budget_service.reserve_scheduler_budget(
            job_id="job-manual-1",
            addon_id="vision",
            cost_units=5,
            payload={"budget_scope": {"node_id": node_id, "money_estimate": 3.0, "compute_units": 10.0}},
            constraints={},
        )

        forced = self.client.post(
            f"/api/system/nodes/budgets/{node_id}/force-release",
            headers={"X-Admin-Token": "test-token"},
            json={"job_id": "job-manual-1", "reason": "operator_release"},
        )
        self.assertEqual(forced.status_code, 200, forced.text)
        self.assertEqual(forced.json()["reservation"]["state"], "released")
        self.assertEqual(forced.json()["reservation"]["release_reason"], "operator_release")

        self.budget_service.reserve_scheduler_budget(
            job_id="job-manual-2",
            addon_id="vision",
            cost_units=4,
            payload={"budget_scope": {"node_id": node_id, "money_estimate": 1.0, "compute_units": 5.0}},
            constraints={},
        )
        reset = self.client.post(
            f"/api/system/nodes/budgets/{node_id}/reset",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertEqual(reset.json()["budget"]["usage_summary"]["node"]["reserved_money"], 0.0)

        event_types = [item["event_type"] for item in self._audit_events()]
        self.assertIn("node_budget_topped_up", event_types)
        self.assertIn("node_budget_override_set", event_types)
        self.assertIn("node_budget_reservation_force_released", event_types)
        self.assertIn("node_budget_reset", event_types)

    def test_admin_can_export_budget_usage_as_json_and_csv(self) -> None:
        node_id, trust_token = self._trusted_node()
        declared = self.client.post(
            "/api/system/nodes/budgets/declaration",
            headers={"X-Node-Trust-Token": trust_token},
            json={"node_id": node_id},
        )
        self.assertEqual(declared.status_code, 200, declared.text)
        configured = self.client.put(
            f"/api/system/nodes/budgets/{node_id}",
            headers={"X-Admin-Token": "test-token"},
            json={"node_budget": {"node_money_limit": 10.0, "node_compute_limit": 100.0}},
        )
        self.assertEqual(configured.status_code, 200, configured.text)
        self.budget_service.reserve_scheduler_budget(
            job_id="job-export-1",
            addon_id="vision",
            cost_units=6,
            payload={"budget_scope": {"node_id": node_id, "money_estimate": 2.0}},
            constraints={},
        )

        json_export = self.client.get(
            f"/api/system/nodes/budgets/export?node_id={node_id}",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(json_export.status_code, 200, json_export.text)
        self.assertEqual(json_export.json()["items"][0]["node_id"], node_id)

        csv_export = self.client.get(
            f"/api/system/nodes/budgets/export?node_id={node_id}&format=csv",
            headers={"X-Admin-Token": "test-token"},
        )
        self.assertEqual(csv_export.status_code, 200, csv_export.text)
        self.assertEqual(csv_export.headers["content-type"].split(";")[0], "text/csv")
        self.assertIn("node_id,scope_kind", csv_export.text)


if __name__ == "__main__":
    unittest.main()
