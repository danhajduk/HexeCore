import tempfile
import unittest
from pathlib import Path

from app.system.onboarding.governance_status import NodeGovernanceStatusService, NodeGovernanceStatusStore


class TestNodeGovernanceStatusStore(unittest.TestCase):
    def test_tracks_issued_and_refresh_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = NodeGovernanceStatusStore(path=Path(tmpdir) / "node_governance_status.json")
            service = NodeGovernanceStatusService(store)

            issued = service.mark_issued(
                node_id="node-a",
                governance_version="gov-v1",
                issued_timestamp="2026-03-11T10:00:00+00:00",
            )
            self.assertEqual(issued.node_id, "node-a")
            self.assertEqual(issued.active_governance_version, "gov-v1")
            self.assertEqual(issued.last_issued_timestamp, "2026-03-11T10:00:00+00:00")
            self.assertIsNone(issued.last_refresh_request_timestamp)

            refreshed = service.mark_refresh_request(node_id="node-a", requested_at="2026-03-11T10:01:00+00:00")
            self.assertEqual(refreshed.node_id, "node-a")
            self.assertEqual(refreshed.active_governance_version, "gov-v1")
            self.assertEqual(refreshed.last_issued_timestamp, "2026-03-11T10:00:00+00:00")
            self.assertEqual(refreshed.last_refresh_request_timestamp, "2026-03-11T10:01:00+00:00")

            loaded = NodeGovernanceStatusStore(path=Path(tmpdir) / "node_governance_status.json")
            record = loaded.get("node-a")
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record.active_governance_version, "gov-v1")
            self.assertEqual(record.last_refresh_request_timestamp, "2026-03-11T10:01:00+00:00")


if __name__ == "__main__":
    unittest.main()
