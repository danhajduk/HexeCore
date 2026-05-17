import unittest

from app.edge.models import EdgeTunnelStatus
from app.edge.runtime_status import merge_cloudflared_runtime_status


class TestEdgeRuntimeStatus(unittest.TestCase):
    def test_merge_cloudflared_runtime_status_refreshes_stale_unavailable_status(self) -> None:
        stale = EdgeTunnelStatus(
            configured=True,
            runtime_state="unavailable",
            healthy=False,
            tunnel_id="tun-1",
            tunnel_name="old-name",
            last_error="supervisor_unavailable",
        )

        refreshed = merge_cloudflared_runtime_status(
            stale,
            {
                "exists": True,
                "state": "running",
                "healthy": True,
                "last_error": None,
                "tunnel_id": "tun-1",
                "config_path": "/tmp/cloudflared/config.json",
                "last_started_at": "2026-05-03T00:00:00+00:00",
            },
        )

        self.assertTrue(refreshed.configured)
        self.assertEqual(refreshed.runtime_state, "running")
        self.assertTrue(refreshed.healthy)
        self.assertIsNone(refreshed.last_error)
        self.assertEqual(refreshed.config_path, "/tmp/cloudflared/config.json")
        self.assertEqual(refreshed.last_started_at, "2026-05-03T00:00:00+00:00")
        self.assertIsNotNone(refreshed.updated_at)

    def test_merge_cloudflared_runtime_status_ignores_missing_runtime(self) -> None:
        current = EdgeTunnelStatus(runtime_state="unavailable", healthy=False)

        self.assertEqual(merge_cloudflared_runtime_status(current, {"exists": False}), current)
        self.assertEqual(merge_cloudflared_runtime_status(current, None), current)


if __name__ == "__main__":
    unittest.main()
