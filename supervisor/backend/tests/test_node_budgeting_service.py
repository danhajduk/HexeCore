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

    def test_usage_summary_rolls_up_periodic_grant_reports(self) -> None:
        self.service.configure_node_budget(
            node_id="node-12345678",
            node_budget={"node_money_limit": 10.0, "node_compute_limit": 1000.0, "compute_unit": "tokens"},
            customer_allocations=[
                {"subject_id": "cust-a", "money_limit": 5.0, "compute_limit": 500.0},
            ],
            provider_allocations=[{"subject_id": "openai", "money_limit": 6.0, "compute_limit": 700.0}],
        )

        policy = self.service.budget_policy("node-12345678")
        self.service.report_usage_summary(
            node_id="node-12345678",
            payload={
                "service": "ai.inference",
                "grant_id": policy["grants"][0]["grant_id"],
                "period_start": policy["period_start"],
                "period_end": policy["period_end"],
                "used_requests": 2,
                "used_tokens": 250,
                "used_cost_cents": 125,
                "metadata": {"customer_id": "cust-a", "provider": "openai"},
            },
        )

        summary = self.service.usage_summary("node-12345678")
        self.assertEqual(summary["node"]["actual_money"], 1.25)
        self.assertEqual(summary["node"]["actual_compute"], 250.0)
        self.assertEqual(summary["customers"][0]["actual_money"], 1.25)
        self.assertEqual(summary["providers"][0]["actual_compute"], 250.0)


if __name__ == "__main__":
    unittest.main()
