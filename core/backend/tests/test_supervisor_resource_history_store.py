from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from app.supervisor.resource_history_store import (
    DEFAULT_RESOURCE_HISTORY_RETENTION_SECONDS,
    SupervisorResourceHistoryStore,
    parse_duration_seconds,
)


class TestSupervisorResourceHistoryStore(unittest.TestCase):
    def _store(self, path: Path, *, retention_seconds: int = 60) -> SupervisorResourceHistoryStore:
        return SupervisorResourceHistoryStore(path=path, retention_seconds=retention_seconds)

    def test_default_retention_is_three_days_and_duration_parser_supports_operator_units(self) -> None:
        self.assertEqual(DEFAULT_RESOURCE_HISTORY_RETENTION_SECONDS, 3 * 24 * 60 * 60)
        self.assertEqual(parse_duration_seconds("60s"), 60)
        self.assertEqual(parse_duration_seconds("15m"), 15 * 60)
        self.assertEqual(parse_duration_seconds("24h"), 24 * 60 * 60)
        self.assertEqual(parse_duration_seconds("3d"), DEFAULT_RESOURCE_HISTORY_RETENTION_SECONDS)
        self.assertEqual(parse_duration_seconds("nonsense", default_seconds=42), 42)

    def test_insert_sample_prunes_entries_outside_retention_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            now = time.time()
            store = self._store(Path(tmpdir) / "history.sqlite3", retention_seconds=10)
            try:
                store.insert_sample(scope="host", sampled_at=now - 20, metrics={"cpu_percent_total": 99})
                store.insert_sample(scope="host", sampled_at=now - 5, metrics={"cpu_percent_total": 12})

                samples = store.samples(scope="host", range_value="30s", end_at=now)
            finally:
                store.close()

        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0]["metrics"]["cpu_percent_total"], 12)
        self.assertEqual(samples[0]["resource_id"], "host")

    def test_range_query_and_step_downsampling_keep_latest_point_per_bucket(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            now = time.time()
            store = self._store(Path(tmpdir) / "history.sqlite3", retention_seconds=3600)
            try:
                store.insert_sample(scope="runtime", resource_id="node-1", sampled_at=now - 120, metrics={"cpu_percent": 1})
                store.insert_sample(scope="runtime", resource_id="node-1", sampled_at=now - 80, metrics={"cpu_percent": 2})
                store.insert_sample(scope="runtime", resource_id="node-1", sampled_at=now - 50, metrics={"cpu_percent": 3})
                store.insert_sample(scope="runtime", resource_id="node-1", sampled_at=now - 10, metrics={"cpu_percent": 4})

                samples = store.samples(scope="runtime", resource_id="node-1", range_value="90s", step_value="60s", end_at=now)
            finally:
                store.close()

        self.assertEqual([item["metrics"]["cpu_percent"] for item in samples], [3, 4])

    def test_records_lifecycle_events_with_same_retention_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            now = time.time()
            store = self._store(Path(tmpdir) / "history.sqlite3", retention_seconds=10)
            try:
                store.record_event(scope="runtime", resource_id="node-1", event_type="exit", occurred_at=now - 20)
                store.record_event(
                    scope="runtime",
                    resource_id="node-1",
                    event_type="restart",
                    occurred_at=now - 2,
                    message="operator restart",
                    payload={"action": "restart"},
                )

                events = store.events(scope="runtime", resource_id="node-1", range_value="30s", end_at=now)
            finally:
                store.close()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "restart")
        self.assertEqual(events[0]["message"], "operator restart")
        self.assertEqual(events[0]["payload"]["action"], "restart")

    def test_samples_with_resource_prefix_returns_child_resource_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            now = time.time()
            store = self._store(Path(tmpdir) / "history.sqlite3", retention_seconds=3600)
            try:
                store.insert_sample(scope="runtime_service", resource_id="node-1/api", sampled_at=now - 10, metrics={"cpu_percent": 1})
                store.insert_sample(scope="runtime_service", resource_id="node-1/worker", sampled_at=now - 5, metrics={"cpu_percent": 2})
                store.insert_sample(scope="runtime_service", resource_id="node-2/api", sampled_at=now - 5, metrics={"cpu_percent": 3})

                samples = store.samples_with_resource_prefix(
                    scope="runtime_service",
                    resource_id_prefix="node-1/",
                    range_value="1h",
                    end_at=now,
                )
            finally:
                store.close()

        self.assertEqual([item["resource_id"] for item in samples], ["node-1/api", "node-1/worker"])


if __name__ == "__main__":
    unittest.main()
