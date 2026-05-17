import asyncio
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.system.scheduler.models import JobIntent, JobPriority, QueueJobState, _coerce_priority, _coerce_queue_state
from app.system.scheduler.queue_persist import QueuePersistStore


class TestSchedulerPersistenceCompat(unittest.TestCase):
    def test_coerce_priority_accepts_legacy_enum_string(self) -> None:
        self.assertEqual(_coerce_priority("JobPriority.normal"), JobPriority.normal)
        self.assertEqual(_coerce_priority("normal"), JobPriority.normal)

    def test_coerce_queue_state_accepts_legacy_enum_string(self) -> None:
        self.assertEqual(_coerce_queue_state("QueueJobState.QUEUED"), QueueJobState.QUEUED)
        self.assertEqual(_coerce_queue_state("QUEUED"), QueueJobState.QUEUED)

    def test_queue_persist_loads_legacy_enum_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scheduler.sqlite3"
            store = QueuePersistStore(str(db_path))
            conn = sqlite3.connect(str(db_path))
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO scheduler_jobs (
                  job_id, addon_id, job_type, cost_units, priority,
                  constraints_json, expected_duration_sec, payload_json, time_sensitive,
                  earliest_start_at, deadline_at, max_runtime_sec, tags_json,
                  state, attempts, next_earliest_start_at, lease_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job-1",
                    "addon-a",
                    "task.summarization",
                    1,
                    "JobPriority.normal",
                    "{}",
                    None,
                    "{}",
                    0,
                    None,
                    None,
                    None,
                    "[]",
                    "QueueJobState.QUEUED",
                    0,
                    None,
                    None,
                    now,
                    now,
                ),
            )
            conn.commit()
            conn.close()

            jobs = asyncio.run(store.load_jobs())
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].priority, JobPriority.normal)
            self.assertEqual(jobs[0].state, QueueJobState.QUEUED)

    def test_queue_persist_writes_canonical_enum_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scheduler.sqlite3"
            store = QueuePersistStore(str(db_path))
            now = datetime.now(timezone.utc)
            job = JobIntent(
                job_id="job-2",
                addon_id="addon-a",
                job_type="task.summarization",
                cost_units=1,
                priority=JobPriority.normal,
                state=QueueJobState.QUEUED,
                created_at=now,
                updated_at=now,
            )
            asyncio.run(store.upsert_job(job))

            conn = sqlite3.connect(str(db_path))
            row = conn.execute("SELECT priority, state FROM scheduler_jobs WHERE job_id = ?", ("job-2",)).fetchone()
            conn.close()
            self.assertEqual(row[0], "normal")
            self.assertEqual(row[1], "QUEUED")


if __name__ == "__main__":
    unittest.main()
