import tempfile
import unittest
from pathlib import Path

from app.supervisor.boot_order import load_boot_order_plan


class TestSupervisorBootOrder(unittest.TestCase):
    def test_default_plan_includes_voice_node(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        plan, warnings = load_boot_order_plan(
            base_path=repo_root / "var/supervisor/boot-order.json",
            override_path=repo_root / "var/supervisor/boot-order.override.yaml",
        )

        self.assertEqual(plan["nodes"]["boot_order"].get("voice-node"), 30)
        self.assertEqual(plan["nodes"]["dependencies"].get("voice-node"), None)
        self.assertIn("boot_order_value_invalid:services:voice-node", warnings)


if __name__ == "__main__":
    unittest.main()
