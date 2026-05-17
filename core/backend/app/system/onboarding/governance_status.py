from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    # backend/app/system/onboarding/governance_status.py -> onboarding(0), system(1), app(2), backend(3), repo(4)
    return Path(__file__).resolve().parents[4]


@dataclass
class NodeGovernanceStatusRecord:
    node_id: str
    active_governance_version: str | None
    last_issued_timestamp: str | None
    last_refresh_request_timestamp: str | None
    freshness_state: str | None = None
    freshness_changed_at: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "node_id": self.node_id,
            "active_governance_version": self.active_governance_version,
            "last_issued_timestamp": self.last_issued_timestamp,
            "last_refresh_request_timestamp": self.last_refresh_request_timestamp,
            "freshness_state": self.freshness_state,
            "freshness_changed_at": self.freshness_changed_at,
        }


class NodeGovernanceStatusStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_repo_root() / "data" / "node_governance_status.json")
        self._records: dict[str, NodeGovernanceStatusRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        items = raw.get("items")
        if not isinstance(items, list):
            return
        loaded: dict[str, NodeGovernanceStatusRecord] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("node_id") or "").strip()
            if not node_id:
                continue
            loaded[node_id] = NodeGovernanceStatusRecord(
                node_id=node_id,
                active_governance_version=str(item.get("active_governance_version") or "").strip() or None,
                last_issued_timestamp=str(item.get("last_issued_timestamp") or "").strip() or None,
                last_refresh_request_timestamp=str(item.get("last_refresh_request_timestamp") or "").strip() or None,
                freshness_state=str(item.get("freshness_state") or "").strip() or None,
                freshness_changed_at=str(item.get("freshness_changed_at") or "").strip() or None,
            )
        self._records = loaded

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "items": [self._records[node_id].to_dict() for node_id in sorted(self._records.keys())],
        }
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def get(self, node_id: str) -> NodeGovernanceStatusRecord | None:
        return self._records.get(str(node_id or "").strip())

    def list(self) -> list[NodeGovernanceStatusRecord]:
        return [self._records[node_id] for node_id in sorted(self._records.keys())]

    def upsert(
        self,
        *,
        node_id: str,
        active_governance_version: str | None = None,
        last_issued_timestamp: str | None = None,
        last_refresh_request_timestamp: str | None = None,
        freshness_state: str | None = None,
        freshness_changed_at: str | None = None,
    ) -> NodeGovernanceStatusRecord:
        node_key = str(node_id or "").strip()
        if not node_key:
            raise ValueError("node_id_required")
        existing = self._records.get(node_key)
        record = NodeGovernanceStatusRecord(
            node_id=node_key,
            active_governance_version=(
                str(active_governance_version or "").strip() or (existing.active_governance_version if existing else None)
            ),
            last_issued_timestamp=(
                str(last_issued_timestamp or "").strip() or (existing.last_issued_timestamp if existing else None)
            ),
            last_refresh_request_timestamp=(
                str(last_refresh_request_timestamp or "").strip()
                or (existing.last_refresh_request_timestamp if existing else None)
            ),
            freshness_state=str(freshness_state or "").strip() or (existing.freshness_state if existing else None),
            freshness_changed_at=str(freshness_changed_at or "").strip() or (existing.freshness_changed_at if existing else None),
        )
        self._records[node_key] = record
        self._save()
        return record


class NodeGovernanceStatusService:
    def __init__(self, store: NodeGovernanceStatusStore) -> None:
        self._store = store

    def mark_issued(self, *, node_id: str, governance_version: str, issued_timestamp: str) -> NodeGovernanceStatusRecord:
        return self._store.upsert(
            node_id=node_id,
            active_governance_version=governance_version,
            last_issued_timestamp=issued_timestamp or _utcnow_iso(),
        )

    def mark_refresh_request(self, *, node_id: str, requested_at: str | None = None) -> NodeGovernanceStatusRecord:
        return self._store.upsert(
            node_id=node_id,
            last_refresh_request_timestamp=requested_at or _utcnow_iso(),
        )

    def get_status(self, node_id: str) -> NodeGovernanceStatusRecord | None:
        return self._store.get(node_id)

    def list_status(self) -> list[NodeGovernanceStatusRecord]:
        return self._store.list()

    def governance_freshness(
        self,
        node_id: str,
        *,
        now: datetime | None = None,
        critical_after_s: int = 6 * 3600,
        outdated_after_s: int = 24 * 3600,
    ) -> dict[str, Any]:
        record = self._store.get(node_id)
        if record is None:
            return {
                "state": "pending",
                "stale_for_s": None,
                "last_contact_at": None,
                "critical_after_s": critical_after_s,
                "outdated_after_s": outdated_after_s,
                "outdated": False,
            }
        if not str(record.active_governance_version or "").strip():
            return {
                "state": "pending",
                "stale_for_s": None,
                "last_contact_at": None,
                "critical_after_s": critical_after_s,
                "outdated_after_s": outdated_after_s,
                "outdated": False,
            }
        current = now or datetime.now(timezone.utc)
        issued_at = _parse_ts(record.last_issued_timestamp)
        refreshed_at = _parse_ts(record.last_refresh_request_timestamp)
        # Freshness is based on governance refresh activity once the node has started refreshing.
        # Before the first refresh request exists, fall back to the original issuance timestamp.
        reference = refreshed_at or issued_at
        if reference is None:
            return {
                "state": "unknown",
                "stale_for_s": None,
                "last_contact_at": None,
                "critical_after_s": critical_after_s,
                "outdated_after_s": outdated_after_s,
                "outdated": False,
            }
        stale_for_s = max(0, int((current - reference).total_seconds()))
        if stale_for_s >= max(outdated_after_s, critical_after_s):
            state = "outdated"
        elif stale_for_s >= max(critical_after_s, 1):
            state = "critical"
        else:
            state = "fresh"
        return {
            "state": state,
            "stale_for_s": stale_for_s,
            "last_contact_at": reference.astimezone(timezone.utc).isoformat(),
            "critical_after_s": critical_after_s,
            "outdated_after_s": outdated_after_s,
            "outdated": state == "outdated",
            "changed_at": record.freshness_changed_at,
        }

    def record_freshness_state(
        self,
        *,
        node_id: str,
        freshness_state: str,
        changed_at: str | None = None,
    ) -> NodeGovernanceStatusRecord:
        return self._store.upsert(
            node_id=node_id,
            freshness_state=freshness_state,
            freshness_changed_at=changed_at or _utcnow_iso(),
        )


def _parse_ts(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None
