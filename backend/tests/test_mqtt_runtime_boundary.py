import asyncio
import unittest

from app.system.mqtt.runtime_boundary import InMemoryBrokerRuntimeBoundary


class TestMqttRuntimeBoundary(unittest.TestCase):
    def test_runtime_boundary_lifecycle(self) -> None:
        boundary = InMemoryBrokerRuntimeBoundary()

        initial = asyncio.run(boundary.get_status())
        self.assertEqual(initial.state, "stopped")
        self.assertFalse(initial.healthy)

        started = asyncio.run(boundary.ensure_running())
        self.assertEqual(started.state, "running")
        self.assertTrue(started.healthy)

        reloaded = asyncio.run(boundary.reload())
        self.assertEqual(reloaded.state, "running")
        self.assertTrue(reloaded.healthy)

        restarted = asyncio.run(boundary.controlled_restart())
        self.assertEqual(restarted.state, "running")
        self.assertTrue(restarted.healthy)


if __name__ == "__main__":
    unittest.main()
