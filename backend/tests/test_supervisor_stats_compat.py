from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.system.stats.router import router as stats_router


class _FakeSupervisorService:
    def system_stats(self, *, api_metrics=None):
        return {
            "timestamp": 1.0,
            "hostname": "host-a",
            "uptime_s": 10.0,
            "load": {"load1": 0.1, "load5": 0.2, "load15": 0.3},
            "cpu": {"percent_total": 1.0, "percent_per_cpu": [1.0], "cores_logical": 1, "cores_physical": 1},
            "mem": {"total": 1, "available": 1, "used": 0, "free": 1, "percent": 0.0},
            "swap": {"total": 0, "used": 0, "free": 0, "percent": 0.0},
            "disks": {},
            "services": {},
            "net": {
                "total": {
                    "bytes_sent": 0,
                    "bytes_recv": 0,
                    "packets_sent": 0,
                    "packets_recv": 0,
                    "errin": 0,
                    "errout": 0,
                    "dropin": 0,
                    "dropout": 0,
                },
                "per_iface": {},
                "total_rate": None,
                "per_iface_rate": None,
            },
            "api": {},
            "busy_rating": 0.0,
        }

    def system_snapshot(self, *, api_metrics=None, api_snapshot=None, registry=None, quiet_thresholds=None):
        return {
            "collected_at": "2026-03-16T00:00:00Z",
            "host": {"hostname": "host-a"},
            "process": {"rss_bytes": 123},
            "api": {},
            "addons": {},
            "quiet": {
                "quiet_score": 100,
                "state": "QUIET",
                "reasons": ["busy_rating=0.00"],
                "inputs": {"busy_rating": 0.0},
            },
            "errors": {},
        }


class TestSupervisorStatsCompat(unittest.TestCase):
    def test_stats_routes_use_supervisor_service_when_available(self) -> None:
        app = FastAPI()
        app.include_router(stats_router, prefix="/api")
        app.state.supervisor_service = _FakeSupervisorService()
        client = TestClient(app)

        stats_res = client.get("/api/system/stats/current")
        self.assertEqual(stats_res.status_code, 200, stats_res.text)
        self.assertEqual(stats_res.json()["hostname"], "host-a")

        snapshot_res = client.get("/api/system-stats/current")
        self.assertEqual(snapshot_res.status_code, 200, snapshot_res.text)
        self.assertEqual(snapshot_res.json()["host"]["hostname"], "host-a")


if __name__ == "__main__":
    unittest.main()
