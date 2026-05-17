import tempfile
import unittest
from pathlib import Path

from app.system.onboarding import ModelRoutingRegistryService, ModelRoutingRegistryStore, NodeBudgetService, NodeBudgetStore


class TestNodeBudgetingService(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self.routing_store = ModelRoutingRegistryStore(path=base / "model_routing_registry.json")
        self.routing_service = ModelRoutingRegistryService(self.routing_store)
        self.budget_store = NodeBudgetStore(path=base / "node_budgets.json")
        self.service = NodeBudgetService(self.budget_store, self.routing_service)
        self.service.declare_budget_capabilities(
            node_id="node-12345678",
            payload={
                "node_id": "node-12345678",
                "currency": "USD",
                "compute_unit": "cost_units",
                "default_period": "monthly",
                "supports_customer_allocations": True,
                "supports_provider_allocations": True,
                "supported_providers": ["openai", "anthropic"],
            },
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_allocation_math_accepts_ten_dollar_split_across_three_3_point_3_customers(self) -> None:
        bundle = self.service.configure_node_budget(
            node_id="node-12345678",
            node_budget={"node_money_limit": 10.0, "node_compute_limit": 100.0},
            customer_allocations=[
                {"subject_id": "cust-a", "money_limit": 3.3, "compute_limit": 30.0},
                {"subject_id": "cust-b", "money_limit": 3.3, "compute_limit": 30.0},
                {"subject_id": "cust-c", "money_limit": 3.3, "compute_limit": 30.0},
            ],
        )
        self.assertEqual(bundle["setup_status"], "configured")
        self.assertEqual(len(bundle["customer_allocations"]), 3)

    def test_allocation_math_rejects_customer_sum_above_node_total(self) -> None:
        with self.assertRaisesRegex(ValueError, "customer_budget_allocations_exceed_node_money_limit"):
            self.service.configure_node_budget(
                node_id="node-12345678",
                node_budget={"node_money_limit": 10.0, "node_compute_limit": 100.0},
                customer_allocations=[
                    {"subject_id": "cust-a", "money_limit": 3.4, "compute_limit": 30.0},
                    {"subject_id": "cust-b", "money_limit": 3.4, "compute_limit": 30.0},
                    {"subject_id": "cust-c", "money_limit": 3.4, "compute_limit": 30.0},
                ],
            )

    def test_provider_sliced_budgets_support_multiple_providers(self) -> None:
        bundle = self.service.configure_node_budget(
            node_id="node-12345678",
            node_budget={"node_money_limit": 20.0, "node_compute_limit": 200.0},
            provider_allocations=[
                {"subject_id": "openai", "money_limit": 8.0, "compute_limit": 80.0},
                {"subject_id": "anthropic", "money_limit": 7.0, "compute_limit": 70.0},
            ],
        )
        self.assertEqual({item["subject_id"] for item in bundle["provider_allocations"]}, {"openai", "anthropic"})

    def test_duplicate_reservation_for_same_job_is_idempotent(self) -> None:
        self.service.configure_node_budget(
            node_id="node-12345678",
            node_budget={"node_money_limit": 10.0, "node_compute_limit": 100.0},
        )
        first = self.service.reserve_scheduler_budget(
            job_id="job-dup",
            addon_id="vision",
            cost_units=4,
            payload={"budget_scope": {"node_id": "node-12345678", "money_estimate": 1.0}},
            constraints={},
        )
        second = self.service.reserve_scheduler_budget(
            job_id="job-dup",
            addon_id="vision",
            cost_units=4,
            payload={"budget_scope": {"node_id": "node-12345678", "money_estimate": 1.0}},
            constraints={},
        )
        self.assertEqual(first["reservation_id"], second["reservation_id"])
        self.assertEqual(len(self.budget_store.list_reservations(node_id="node-12345678")), 1)

    def test_enforcement_behavior_blocks_node_customer_and_provider_exhaustion(self) -> None:
        self.service.configure_node_budget(
            node_id="node-12345678",
            node_budget={"node_money_limit": 10.0, "node_compute_limit": 100.0},
            customer_allocations=[
                {"subject_id": "cust-a", "money_limit": 3.0, "compute_limit": 30.0},
                {"subject_id": "cust-b", "money_limit": 3.0, "compute_limit": 30.0},
            ],
            provider_allocations=[{"subject_id": "openai", "money_limit": 4.0, "compute_limit": 40.0}],
        )

        self.service.reserve_scheduler_budget(
            job_id="job-ok",
            addon_id="vision",
            cost_units=10,
            payload={"budget_scope": {"node_id": "node-12345678", "customer_id": "cust-a", "provider": "openai", "money_estimate": 2.0}},
            constraints={},
        )

        with self.assertRaisesRegex(ValueError, "customer_money_budget_exceeded"):
            self.service.reserve_scheduler_budget(
                job_id="job-customer",
                addon_id="vision",
                cost_units=10,
                payload={"budget_scope": {"node_id": "node-12345678", "customer_id": "cust-a", "provider": "openai", "money_estimate": 1.5}},
                constraints={},
            )

        with self.assertRaisesRegex(ValueError, "provider_money_budget_exceeded"):
            self.service.reserve_scheduler_budget(
                job_id="job-provider",
                addon_id="vision",
                cost_units=10,
                payload={"budget_scope": {"node_id": "node-12345678", "customer_id": "cust-b", "provider": "openai", "money_estimate": 2.5}},
                constraints={},
            )

        with self.assertRaisesRegex(ValueError, "node_money_budget_exceeded"):
            self.service.reserve_scheduler_budget(
                job_id="job-node",
                addon_id="vision",
                cost_units=10,
                payload={"budget_scope": {"node_id": "node-12345678", "money_estimate": 9.0}},
                constraints={},
            )


if __name__ == "__main__":
    unittest.main()
