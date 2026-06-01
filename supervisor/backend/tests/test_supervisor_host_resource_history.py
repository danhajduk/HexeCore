from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.supervisor import SupervisorDomainService
from app.supervisor.resource_monitor import SupervisorResourceMonitor


class _FakeHistoryStore:
    def __init__(self) -> None:
        self.samples: list[dict[str, object]] = []

    def insert_sample(self, **kwargs):  # noqa: ANN001
        self.samples.append(kwargs)


class _HistorySupervisorService(SupervisorDomainService):
    def _bluetooth_summary(self) -> dict[str, object]:
        return {
            "bluetooth_present": False,
            "bluetooth_powered": False,
            "bluetooth_ensure_powered": False,
            "bluetooth_adapters": [],
        }

    def _network_transport_summary(self) -> dict[str, object]:
        return {"network_primary_type": "ethernet", "network_primary_interface": "eth0"}

    def _internet_summary(self) -> dict[str, object]:
        return {"internet_reachable": True, "internet_check_error": None}


class TestSupervisorHostResourceHistory(unittest.TestCase):
    def _fake_stats(self):
        return SimpleNamespace(
            uptime_s=123.0,
            load=SimpleNamespace(load1=0.1, load5=0.2, load15=0.3),
            cpu=SimpleNamespace(percent_total=12.5, cores_logical=8),
            mem=SimpleNamespace(total=16000, available=8000, percent=50.0),
            swap=SimpleNamespace(total=4000, used=1000, free=3000, percent=25.0),
            disks={"/": SimpleNamespace(total=100000, free=40000, percent=60.0)},
            net=SimpleNamespace(
                total=SimpleNamespace(
                    bytes_recv=100,
                    bytes_sent=200,
                    errin=0,
                    errout=1,
                    dropin=2,
                    dropout=3,
                ),
                total_rate=SimpleNamespace(rx_Bps=10.0, tx_Bps=20.0),
            ),
        )

    def test_resources_summary_persists_host_resource_sample_with_swap_and_gpu_metrics(self) -> None:
        history = _FakeHistoryStore()
        monitor = SupervisorResourceMonitor(
            docker_available=lambda: False,
            systemctl_available=lambda: False,
            gpu_available=lambda: False,
        )
        service = _HistorySupervisorService(resource_monitor=monitor, resource_history_store=history)

        with patch("app.supervisor.service.collect_system_stats", return_value=self._fake_stats()):
            summary = service.resources_summary()

        self.assertEqual(summary.cpu_percent_total, 12.5)
        self.assertEqual(len(history.samples), 1)
        sample = history.samples[0]
        self.assertEqual(sample["scope"], "host")
        self.assertEqual(sample["resource_id"], "host")
        metrics = sample["metrics"]
        self.assertEqual(metrics["cpu_percent_total"], 12.5)
        self.assertEqual(metrics["memory_percent"], 50.0)
        self.assertEqual(metrics["swap_total_bytes"], 4000)
        self.assertEqual(metrics["swap_percent"], 25.0)
        self.assertEqual(metrics["root_disk_percent"], 60.0)
        self.assertEqual(metrics["network_rx_Bps"], 10.0)
        self.assertEqual(metrics["gpu_count"], 0)
        metadata = sample["metadata"]
        self.assertEqual(metadata["resource_observer"], "supervisor")
        self.assertTrue(metadata["supervisor_id"])

    def test_resource_history_errors_do_not_break_resource_summary(self) -> None:
        class BrokenHistoryStore:
            def insert_sample(self, **kwargs):  # noqa: ANN001
                raise RuntimeError("history offline")

        service = _HistorySupervisorService(
            resource_monitor=SupervisorResourceMonitor(gpu_available=lambda: False),
            resource_history_store=BrokenHistoryStore(),
        )

        with patch("app.supervisor.service.collect_system_stats", return_value=self._fake_stats()):
            summary = service.resources_summary()

        self.assertEqual(summary.cpu_percent_total, 12.5)


if __name__ == "__main__":
    unittest.main()
