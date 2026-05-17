import subprocess
import unittest
from unittest.mock import patch

from app.system.stats.service import collect_service_statuses


class TestSystemStatsService(unittest.TestCase):
    @patch("app.system.stats.service.shutil.which", return_value="/usr/bin/systemctl")
    @patch("app.system.stats.service.subprocess.run")
    def test_collect_service_statuses_parses_running_state(self, run_mock, _which_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="loaded\nactive\nrunning\nenabled\n",
            stderr="",
        )

        statuses = collect_service_statuses()

        self.assertIn("backend", statuses)
        backend = statuses["backend"]
        self.assertTrue(backend.running)
        self.assertTrue(backend.available)
        self.assertEqual(backend.active_state, "active")
        self.assertEqual(backend.sub_state, "running")
        self.assertEqual(run_mock.call_count, 4)

    @patch("app.system.stats.service.shutil.which", return_value=None)
    def test_collect_service_statuses_when_systemctl_missing(self, _which_mock) -> None:
        statuses = collect_service_statuses()
        self.assertIn("supervisor", statuses)
        self.assertFalse(statuses["supervisor"].available)
        self.assertEqual(statuses["supervisor"].error, "systemctl_not_found")


if __name__ == "__main__":
    unittest.main()
