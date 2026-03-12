from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .capability_profiles import NodeCapabilityProfileRecord

GOVERNANCE_SCHEMA_VERSION = "1"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    # backend/app/system/onboarding/governance.py -> onboarding(0), system(1), app(2), backend(3), repo(4)
    return Path(__file__).resolve().parents[4]


@dataclass
class NodeGovernanceBundleRecord:
    node_id: str
    capability_profile_id: str
    governance_version: str
    issued_timestamp: str
    node_class_rules: dict[str, Any]
    feature_gating_defaults: dict[str, bool]
    telemetry_requirements: dict[str, Any]
    capability_usage_constraints: dict[str, Any]
    schema_version: str = GOVERNANCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "capability_profile_id": self.capability_profile_id,
            "governance_version": self.governance_version,
            "issued_timestamp": self.issued_timestamp,
            "node_class_rules": dict(self.node_class_rules or {}),
            "feature_gating_defaults": dict(self.feature_gating_defaults or {}),
            "telemetry_requirements": dict(self.telemetry_requirements or {}),
            "capability_usage_constraints": dict(self.capability_usage_constraints or {}),
        }


class NodeGovernanceStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_repo_root() / "data" / "node_governance_bundles.json")
        self._items: list[NodeGovernanceBundleRecord] = []
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
        loaded: list[NodeGovernanceBundleRecord] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("node_id") or "").strip()
            profile_id = str(item.get("capability_profile_id") or "").strip()
            gov_version = str(item.get("governance_version") or "").strip()
            issued = str(item.get("issued_timestamp") or "").strip()
            if not (node_id and profile_id and gov_version and issued):
                continue
            loaded.append(
                NodeGovernanceBundleRecord(
                    node_id=node_id,
                    capability_profile_id=profile_id,
                    governance_version=gov_version,
                    issued_timestamp=issued,
                    node_class_rules=item.get("node_class_rules") if isinstance(item.get("node_class_rules"), dict) else {},
                    feature_gating_defaults=(
                        item.get("feature_gating_defaults") if isinstance(item.get("feature_gating_defaults"), dict) else {}
                    ),
                    telemetry_requirements=(
                        item.get("telemetry_requirements") if isinstance(item.get("telemetry_requirements"), dict) else {}
                    ),
                    capability_usage_constraints=(
                        item.get("capability_usage_constraints")
                        if isinstance(item.get("capability_usage_constraints"), dict)
                        else {}
                    ),
                    schema_version=str(item.get("schema_version") or GOVERNANCE_SCHEMA_VERSION),
                )
            )
        self._items = loaded

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": GOVERNANCE_SCHEMA_VERSION,
            "items": [item.to_dict() for item in self._items],
        }
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def list(self, *, node_id: str | None = None) -> list[NodeGovernanceBundleRecord]:
        node_key = str(node_id or "").strip()
        if not node_key:
            return list(self._items)
        return [item for item in self._items if item.node_id == node_key]

    def latest_for_node(self, node_id: str) -> NodeGovernanceBundleRecord | None:
        node_key = str(node_id or "").strip()
        if not node_key:
            return None
        items = [item for item in self._items if item.node_id == node_key]
        if not items:
            return None
        return items[-1]

    def append(self, record: NodeGovernanceBundleRecord) -> NodeGovernanceBundleRecord:
        self._items.append(record)
        self._save()
        return record


class NodeGovernanceService:
    def __init__(self, store: NodeGovernanceStore) -> None:
        self._store = store

    def get_current_for_node(self, *, node_id: str, capability_profile_id: str | None = None) -> NodeGovernanceBundleRecord | None:
        latest = self._store.latest_for_node(node_id)
        if latest is None:
            return None
        profile_id = str(capability_profile_id or "").strip()
        if profile_id and latest.capability_profile_id != profile_id:
            return None
        return latest

    def issue_baseline_for_profile(
        self,
        *,
        node_id: str,
        node_type: str,
        profile: NodeCapabilityProfileRecord,
    ) -> NodeGovernanceBundleRecord:
        latest = self._store.latest_for_node(node_id)
        if latest is not None and latest.capability_profile_id == profile.profile_id:
            return latest

        next_revision = 1
        if latest is not None:
            raw = str(latest.governance_version or "")
            if raw.startswith("gov-v"):
                try:
                    next_revision = int(raw[len("gov-v") :]) + 1
                except Exception:
                    next_revision = 1
        governance_version = f"gov-v{next_revision}"
        feature_flags = dict(profile.feature_flags or {})
        record = NodeGovernanceBundleRecord(
            node_id=node_id,
            capability_profile_id=profile.profile_id,
            governance_version=governance_version,
            issued_timestamp=_utcnow_iso(),
            node_class_rules={
                "node_type": str(node_type or ""),
                "profile_id": profile.profile_id,
            },
            feature_gating_defaults={
                "allow_provider_failover": bool(feature_flags.get("provider_failover", False)),
                "allow_governance_refresh": bool(feature_flags.get("governance_refresh", False)),
            },
            telemetry_requirements={
                "required": bool(feature_flags.get("telemetry", False)),
                "lifecycle_events_required": bool(feature_flags.get("lifecycle_events", False)),
                "min_report_interval_s": 30,
            },
            capability_usage_constraints={
                "declared_task_families": list(profile.declared_task_families or []),
                "enabled_providers": list(profile.enabled_providers or []),
                "max_concurrent_tasks": 2,
            },
        )
        return self._store.append(record)
