from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from app.core.env import getenv


SUPERVISOR_RESOURCE_HISTORY_SCHEMA_VERSION = "1"
DEFAULT_RESOURCE_HISTORY_RETENTION_SECONDS = 3 * 24 * 60 * 60
DEFAULT_RESOURCE_HISTORY_PRUNE_INTERVAL_SECONDS = 5 * 60

DDL = """
CREATE TABLE IF NOT EXISTS supervisor_resource_samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scope TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  sampled_at REAL NOT NULL,
  sampled_at_iso TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_supervisor_resource_samples_lookup
  ON supervisor_resource_samples(scope, resource_id, sampled_at);

CREATE INDEX IF NOT EXISTS idx_supervisor_resource_samples_sampled_at
  ON supervisor_resource_samples(sampled_at);

CREATE TABLE IF NOT EXISTS supervisor_resource_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scope TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  occurred_at REAL NOT NULL,
  occurred_at_iso TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_supervisor_resource_events_lookup
  ON supervisor_resource_events(scope, resource_id, occurred_at);

CREATE INDEX IF NOT EXISTS idx_supervisor_resource_events_occurred_at
  ON supervisor_resource_events(occurred_at);
"""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _utcnow_ts() -> float:
    return time.time()


def _iso_from_ts(value: float) -> str:
    return datetime.fromtimestamp(float(value), timezone.utc).isoformat()


def _timestamp(value: float | int | str | datetime | None) -> float:
    if value is None:
        return _utcnow_ts()
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return _utcnow_ts()
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def parse_duration_seconds(value: object, *, default_seconds: int = DEFAULT_RESOURCE_HISTORY_RETENTION_SECONDS) -> int:
    if value is None:
        return int(default_seconds)
    if isinstance(value, bool):
        return int(default_seconds)
    if isinstance(value, int | float):
        return max(1, int(value))
    raw = str(value or "").strip().lower()
    if not raw:
        return int(default_seconds)
    units = {
        "s": 1,
        "sec": 1,
        "secs": 1,
        "second": 1,
        "seconds": 1,
        "m": 60,
        "min": 60,
        "mins": 60,
        "minute": 60,
        "minutes": 60,
        "h": 60 * 60,
        "hr": 60 * 60,
        "hrs": 60 * 60,
        "hour": 60 * 60,
        "hours": 60 * 60,
        "d": 24 * 60 * 60,
        "day": 24 * 60 * 60,
        "days": 24 * 60 * 60,
    }
    number = ""
    unit = ""
    for char in raw:
        if char.isdigit() or char == ".":
            number += char
        elif not char.isspace():
            unit += char
    try:
        amount = float(number)
    except Exception:
        return int(default_seconds)
    multiplier = units.get(unit or "s")
    if multiplier is None:
        return int(default_seconds)
    return max(1, int(amount * multiplier))


class SupervisorResourceHistoryStore:
    def __init__(
        self,
        path: Path | None = None,
        *,
        retention_seconds: int | None = None,
    ) -> None:
        configured_path = str(getenv("HEXE_SUPERVISOR_RESOURCE_HISTORY_PATH", "") or "").strip()
        self._path = path or Path(configured_path) if configured_path else path or (_repo_root() / "data" / "supervisor_resource_history.sqlite3")
        raw_retention = getenv("HEXE_SUPERVISOR_RESOURCE_HISTORY_RETENTION") or getenv(
            "HEXE_SUPERVISOR_RESOURCE_HISTORY_RETENTION_SECONDS"
        )
        raw_prune_interval = getenv("HEXE_SUPERVISOR_RESOURCE_HISTORY_PRUNE_INTERVAL") or getenv(
            "HEXE_SUPERVISOR_RESOURCE_HISTORY_PRUNE_INTERVAL_SECONDS"
        )
        self.retention_seconds = int(
            retention_seconds
            if retention_seconds is not None
            else parse_duration_seconds(raw_retention, default_seconds=DEFAULT_RESOURCE_HISTORY_RETENTION_SECONDS)
        )
        self.prune_interval_seconds = parse_duration_seconds(
            raw_prune_interval,
            default_seconds=DEFAULT_RESOURCE_HISTORY_PRUNE_INTERVAL_SECONDS,
        )
        self._last_prune_ts = 0.0
        self._lock = RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.executescript(DDL)
        self._conn.commit()

    @property
    def path(self) -> Path:
        return self._path

    def insert_sample(
        self,
        *,
        scope: str,
        metrics: dict[str, Any],
        resource_id: str | None = None,
        sampled_at: float | int | str | datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_scope = self._clean_scope(scope)
        clean_resource_id = self._clean_resource_id(resource_id)
        ts = _timestamp(sampled_at)
        sampled_at_iso = _iso_from_ts(ts)
        payload = {
            "schema_version": SUPERVISOR_RESOURCE_HISTORY_SCHEMA_VERSION,
            "scope": clean_scope,
            "resource_id": clean_resource_id,
            "sampled_at": sampled_at_iso,
            "metrics": dict(metrics or {}),
            "metadata": dict(metadata or {}),
        }
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO supervisor_resource_samples(scope, resource_id, sampled_at, sampled_at_iso, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (clean_scope, clean_resource_id, ts, sampled_at_iso, json.dumps(payload, separators=(",", ":"), sort_keys=True)),
            )
            self._conn.commit()
            self.prune_if_due()
        return payload

    def record_event(
        self,
        *,
        scope: str,
        event_type: str,
        resource_id: str | None = None,
        occurred_at: float | int | str | datetime | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_scope = self._clean_scope(scope)
        clean_resource_id = self._clean_resource_id(resource_id)
        clean_event_type = str(event_type or "").strip() or "event"
        ts = _timestamp(occurred_at)
        occurred_at_iso = _iso_from_ts(ts)
        event_payload = {
            "schema_version": SUPERVISOR_RESOURCE_HISTORY_SCHEMA_VERSION,
            "scope": clean_scope,
            "resource_id": clean_resource_id,
            "event_type": clean_event_type,
            "occurred_at": occurred_at_iso,
            "message": str(message or "").strip() or None,
            "payload": dict(payload or {}),
        }
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO supervisor_resource_events(scope, resource_id, event_type, occurred_at, occurred_at_iso, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_scope,
                    clean_resource_id,
                    clean_event_type,
                    ts,
                    occurred_at_iso,
                    json.dumps(event_payload, separators=(",", ":"), sort_keys=True),
                ),
            )
            self._conn.commit()
            self.prune_if_due()
        return event_payload

    def samples(
        self,
        *,
        scope: str,
        resource_id: str | None = None,
        range_value: object = None,
        step_value: object = None,
        end_at: float | int | str | datetime | None = None,
    ) -> list[dict[str, Any]]:
        clean_scope = self._clean_scope(scope)
        clean_resource_id = self._clean_resource_id(resource_id)
        end_ts = _timestamp(end_at)
        range_seconds = parse_duration_seconds(range_value, default_seconds=self.retention_seconds)
        start_ts = end_ts - range_seconds
        with self._lock:
            rows = self._sample_rows(clean_scope, clean_resource_id, start_ts, end_ts)
        points = [self._load_payload(row[0]) for row in rows]
        return self._downsample(points, start_ts=start_ts, step_seconds=parse_duration_seconds(step_value, default_seconds=0) if step_value else 0)

    def samples_with_resource_prefix(
        self,
        *,
        scope: str,
        resource_id_prefix: str,
        range_value: object = None,
        step_value: object = None,
        end_at: float | int | str | datetime | None = None,
    ) -> list[dict[str, Any]]:
        clean_scope = self._clean_scope(scope)
        clean_prefix = str(resource_id_prefix or "").strip()
        end_ts = _timestamp(end_at)
        range_seconds = parse_duration_seconds(range_value, default_seconds=self.retention_seconds)
        start_ts = end_ts - range_seconds
        with self._lock:
            rows = self._sample_prefix_rows(clean_scope, clean_prefix, start_ts, end_ts)
        points = [self._load_payload(row[0]) for row in rows]
        return self._downsample(points, start_ts=start_ts, step_seconds=parse_duration_seconds(step_value, default_seconds=0) if step_value else 0)

    def events(
        self,
        *,
        scope: str,
        resource_id: str | None = None,
        range_value: object = None,
        end_at: float | int | str | datetime | None = None,
    ) -> list[dict[str, Any]]:
        clean_scope = self._clean_scope(scope)
        clean_resource_id = self._clean_resource_id(resource_id)
        end_ts = _timestamp(end_at)
        range_seconds = parse_duration_seconds(range_value, default_seconds=self.retention_seconds)
        start_ts = end_ts - range_seconds
        with self._lock:
            rows = self._event_rows(clean_scope, clean_resource_id, start_ts, end_ts)
        return [self._load_payload(row[0]) for row in rows]

    def prune_if_due(self, *, now_ts: float | None = None, force: bool = False) -> None:
        now = float(now_ts if now_ts is not None else _utcnow_ts())
        if not force and (now - self._last_prune_ts) < float(self.prune_interval_seconds):
            return
        self.prune(now_ts=now)

    def prune(self, *, now_ts: float | None = None) -> None:
        cutoff = float(now_ts if now_ts is not None else _utcnow_ts()) - float(self.retention_seconds)
        with self._lock:
            self._conn.execute("DELETE FROM supervisor_resource_samples WHERE sampled_at < ?", (cutoff,))
            self._conn.execute("DELETE FROM supervisor_resource_events WHERE occurred_at < ?", (cutoff,))
            self._conn.commit()
            self._last_prune_ts = float(now_ts if now_ts is not None else _utcnow_ts())

    def status(self) -> dict[str, Any]:
        with self._lock:
            sample_count = int(self._conn.execute("SELECT COUNT(*) FROM supervisor_resource_samples").fetchone()[0])
            event_count = int(self._conn.execute("SELECT COUNT(*) FROM supervisor_resource_events").fetchone()[0])
            sample_bounds = self._conn.execute(
                "SELECT MIN(sampled_at), MAX(sampled_at) FROM supervisor_resource_samples"
            ).fetchone()
            event_bounds = self._conn.execute(
                "SELECT MIN(occurred_at), MAX(occurred_at) FROM supervisor_resource_events"
            ).fetchone()
            page_size = int(self._conn.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(self._conn.execute("PRAGMA page_count").fetchone()[0])
            freelist_count = int(self._conn.execute("PRAGMA freelist_count").fetchone()[0])
        size_bytes = self._file_size(self._path)
        wal_size_bytes = self._file_size(self._wal_path())
        shm_size_bytes = self._file_size(self._shm_path())
        return {
            "path": str(self._path),
            "exists": self._path.exists(),
            "size_bytes": size_bytes,
            "wal_size_bytes": wal_size_bytes,
            "shm_size_bytes": shm_size_bytes,
            "total_size_bytes": size_bytes + wal_size_bytes + shm_size_bytes,
            "page_size_bytes": page_size,
            "page_count": page_count,
            "freelist_count": freelist_count,
            "free_bytes": page_size * freelist_count,
            "retention_seconds": int(self.retention_seconds),
            "prune_interval_seconds": int(self.prune_interval_seconds),
            "last_prune_at": _iso_from_ts(self._last_prune_ts) if self._last_prune_ts > 0 else None,
            "sample_count": sample_count,
            "event_count": event_count,
            "oldest_sample_at": self._iso_or_none(sample_bounds[0]),
            "newest_sample_at": self._iso_or_none(sample_bounds[1]),
            "oldest_event_at": self._iso_or_none(event_bounds[0]),
            "newest_event_at": self._iso_or_none(event_bounds[1]),
        }

    def maintain(self, *, action: str = "compact", now_ts: float | None = None) -> dict[str, Any]:
        clean_action = str(action or "compact").strip().lower()
        allowed_actions = {"prune", "checkpoint", "vacuum", "compact"}
        if clean_action not in allowed_actions:
            raise ValueError("unsupported_resource_history_maintenance_action")
        before = self.status()
        with self._lock:
            if clean_action in {"prune", "compact"}:
                self.prune_if_due(now_ts=now_ts, force=True)
            if clean_action in {"checkpoint", "compact"}:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);").fetchall()
            if clean_action in {"vacuum", "compact"}:
                self._conn.commit()
                self._conn.execute("VACUUM;")
                self._conn.commit()
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);").fetchall()
        return {
            "ok": True,
            "action": clean_action,
            "before": before,
            "after": self.status(),
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _wal_path(self) -> Path:
        return self._path.with_name(f"{self._path.name}-wal")

    def _shm_path(self) -> Path:
        return self._path.with_name(f"{self._path.name}-shm")

    def _file_size(self, path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def _iso_or_none(self, value: object) -> str | None:
        if value is None:
            return None
        return _iso_from_ts(float(value))

    def _sample_rows(self, scope: str, resource_id: str, start_ts: float, end_ts: float) -> list[tuple[str]]:
        return self._conn.execute(
            """
            SELECT payload_json FROM supervisor_resource_samples
            WHERE scope = ? AND resource_id = ? AND sampled_at >= ? AND sampled_at <= ?
            ORDER BY sampled_at ASC, id ASC
            """,
            (scope, resource_id, start_ts, end_ts),
        ).fetchall()

    def _sample_prefix_rows(self, scope: str, resource_id_prefix: str, start_ts: float, end_ts: float) -> list[tuple[str]]:
        return self._conn.execute(
            """
            SELECT payload_json FROM supervisor_resource_samples
            WHERE scope = ? AND resource_id LIKE ? AND sampled_at >= ? AND sampled_at <= ?
            ORDER BY sampled_at ASC, id ASC
            """,
            (scope, f"{resource_id_prefix}%", start_ts, end_ts),
        ).fetchall()

    def _event_rows(self, scope: str, resource_id: str, start_ts: float, end_ts: float) -> list[tuple[str]]:
        return self._conn.execute(
            """
            SELECT payload_json FROM supervisor_resource_events
            WHERE scope = ? AND resource_id = ? AND occurred_at >= ? AND occurred_at <= ?
            ORDER BY occurred_at ASC, id ASC
            """,
            (scope, resource_id, start_ts, end_ts),
        ).fetchall()

    def _downsample(self, points: list[dict[str, Any]], *, start_ts: float, step_seconds: int) -> list[dict[str, Any]]:
        if step_seconds <= 0 or len(points) <= 1:
            return points
        buckets: dict[int, dict[str, Any]] = {}
        for point in points:
            ts = _timestamp(point.get("sampled_at"))
            bucket = int((ts - start_ts) // step_seconds)
            buckets[bucket] = point
        return [buckets[key] for key in sorted(buckets)]

    def _load_payload(self, value: str) -> dict[str, Any]:
        try:
            payload = json.loads(value)
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _clean_scope(self, scope: str) -> str:
        clean = str(scope or "").strip().lower()
        if not clean:
            raise ValueError("resource_history_scope_required")
        return clean

    def _clean_resource_id(self, resource_id: str | None) -> str:
        clean = str(resource_id or "").strip()
        return clean or "host"
