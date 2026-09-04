from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.supervisor.config import supervisor_reported_version
from app.api.admin import require_admin_token
from app.supervisor.update_package import SupervisorUpdatePackageError, build_supervisor_update_package

SUPERVISOR_REGISTRY_SCHEMA_VERSION = "1"
SUPERVISOR_ENROLLMENT_SCHEMA_VERSION = "1"
SERVICE_TELEMETRY_KEYS = (
    "rps",
    "latency_ms_avg",
    "latency_ms_p95",
    "error_rate",
    "inflight",
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _workspace_root() -> Path:
    return _repo_root().parent


def _clean_text(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _stale_after_s() -> float:
    raw = str(os.getenv("HEXE_SUPERVISOR_FLEET_STALE_S", "60")).strip()
    try:
        return max(1.0, float(raw))
    except Exception:
        return 60.0


def _offline_after_s() -> float:
    raw = str(os.getenv("HEXE_SUPERVISOR_FLEET_OFFLINE_S", "180")).strip()
    try:
        return max(_stale_after_s() + 1.0, float(raw))
    except Exception:
        return 180.0


def _local_probe_cache_s() -> float:
    raw = str(os.getenv("HEXE_SUPERVISOR_FLEET_LOCAL_CACHE_S", "10")).strip()
    try:
        return max(1.0, float(raw))
    except Exception:
        return 10.0


def _historical_after_s() -> float:
    raw = str(os.getenv("HEXE_SUPERVISOR_FLEET_HISTORICAL_S", str(7 * 24 * 60 * 60))).strip()
    try:
        return max(_offline_after_s() + 1.0, float(raw))
    except Exception:
        return float(7 * 24 * 60 * 60)


def _supervisor_history_timeout_s() -> float:
    raw = str(os.getenv("HEXE_SUPERVISOR_HISTORY_TIMEOUT_S") or os.getenv("HEXE_SUPERVISOR_API_TIMEOUT_S") or "5.0").strip()
    try:
        return min(max(1.0, float(raw)), 60.0)
    except Exception:
        return 5.0


def _supervisor_package_source_root() -> Path:
    configured = _clean_text(os.getenv("HEXE_SUPERVISOR_PACKAGE_SOURCE_ROOT"))
    if configured:
        return Path(configured).expanduser()
    sibling = _workspace_root() / "supervisor"
    return sibling if sibling.exists() else _repo_root()


def _source_commit_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(_workspace_root()), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except Exception:
        return None
    sha = (result.stdout or "").strip()
    return sha if result.returncode == 0 and sha else None


def _bluetooth_access_policy() -> str:
    value = _clean_text(os.getenv("HEXE_BLUETOOTH_ACCESS_POLICY"), "disabled").lower()
    if value in {"disabled", "ask", "trusted_only", "allowed"}:
        return value
    return "disabled"


def _supervisor_capabilities(resources: dict[str, Any], *, local_core_attached: bool = False) -> list[str]:
    capabilities = [
        "host_resources",
        "runtime_inventory",
        "node_runtime_registry",
        "core_runtime_registry",
    ]
    if bool(resources.get("bluetooth_present")):
        capabilities.extend(["bluetooth", "bluetooth_governance"])
    if local_core_attached:
        capabilities.append("local_core_attached")
    return capabilities


def _supervisor_metadata(resources: dict[str, Any], *, reporter: str, attached_to_core: bool = False) -> dict[str, Any]:
    metadata: dict[str, Any] = {"reporter": reporter}
    if attached_to_core:
        metadata["attached_to_core"] = True
    if bool(resources.get("bluetooth_present")):
        metadata["bluetooth"] = {
            "present": True,
            "powered": bool(resources.get("bluetooth_powered")),
            "ensure_powered": bool(resources.get("bluetooth_ensure_powered")),
            "power_error": resources.get("bluetooth_power_error"),
            "policy": _bluetooth_access_policy(),
            "governed_by_core": True,
        }
    return metadata


def _freshness_state(last_seen_at: str | None) -> str:
    if not last_seen_at:
        return "offline"
    try:
        seen = datetime.fromisoformat(str(last_seen_at).replace("Z", "+00:00"))
    except Exception:
        return "offline"
    age_s = max(0.0, (datetime.now(timezone.utc) - seen).total_seconds())
    if age_s >= _offline_after_s():
        return "offline"
    if age_s >= _stale_after_s():
        return "stale"
    return "online"


def _freshness_age_s(last_seen_at: str | None) -> float | None:
    seen = _parse_iso(last_seen_at)
    if seen is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - seen).total_seconds())


def _freshness_reason(record: "SupervisorFleetRecord", *, visibility_reason: str | None = None) -> str:
    if visibility_reason == "superseded_local_supervisor":
        return "superseded_by_newer_local_supervisor"
    state = _freshness_state(record.last_seen_at)
    if not record.last_seen_at:
        return "no_heartbeat"
    if state == "offline":
        return "heartbeat_offline"
    if state == "stale":
        return "heartbeat_stale"
    return "heartbeat_fresh"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _dict_payload(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_payload(value: object) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _numeric_metrics_payload(value: object, keys: tuple[str, ...] = SERVICE_TELEMETRY_KEYS) -> dict[str, int | float]:
    payload = dict(value) if isinstance(value, dict) else {}
    metrics: dict[str, int | float] = {}
    for key in keys:
        raw = payload.get(key)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, int | float):
            metrics[key] = raw
            continue
        try:
            parsed = float(str(raw).strip())
        except Exception:
            continue
        metrics[key] = parsed
    return metrics


def _sanitize_update_payload(value: object, *, depth: int = 0) -> Any:
    if depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(marker in lowered for marker in ("token", "password", "secret", "credential", "private_key", "authorization")):
                clean[key_text] = "[REDACTED]"
            else:
                clean[key_text] = _sanitize_update_payload(item, depth=depth + 1)
        return clean
    if isinstance(value, list):
        return [_sanitize_update_payload(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in ("token=", "password=", "secret=", "authorization:", "credential")):
            return "[REDACTED]"
        return value[:4000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:1000]


def _current_core_api_metrics(request: Request) -> dict[str, int | float]:
    latest = getattr(request.app.state, "latest_api_metrics", None)
    metrics = _numeric_metrics_payload(latest)
    if metrics:
        return metrics
    collector = getattr(request.app.state, "api_metrics", None)
    snapshot = getattr(collector, "snapshot", None)
    if not callable(snapshot):
        return {}
    try:
        return _numeric_metrics_payload(snapshot(window_s=60, top_n=10))
    except Exception:
        return {}


def _with_local_core_runtime_telemetry(items: list[dict[str, Any]], request: Request) -> list[dict[str, Any]]:
    core_api_metrics = _current_core_api_metrics(request)
    if not core_api_metrics:
        return [dict(item) for item in items]
    enriched: list[dict[str, Any]] = []
    for item in items:
        runtime = dict(item)
        if _clean_text(runtime.get("runtime_id")) == "core-api":
            usage = dict(runtime.get("resource_usage") or {}) if isinstance(runtime.get("resource_usage"), dict) else {}
            usage.update(core_api_metrics)
            runtime["resource_usage"] = usage
        enriched.append(runtime)
    return enriched


def _history_params(range_value: str, step_value: str | None) -> dict[str, str]:
    params = {"range": _clean_text(range_value, "24h")}
    if _clean_text(step_value):
        params["step"] = _clean_text(step_value)
    return params


def _is_local_supervisor_record(record: "SupervisorFleetRecord") -> bool:
    transport = _clean_text(record.transport).lower()
    metadata = dict(record.metadata or {})
    return transport == "local" or metadata.get("attached_to_core") is True


def _record_age_anchor(record: "SupervisorFleetRecord") -> datetime | None:
    return _parse_iso(record.last_seen_at) or _parse_iso(record.updated_at) or _parse_iso(record.first_seen_at)


def _local_supervisor_host_key(record: "SupervisorFleetRecord") -> str:
    return (_clean_text(record.hostname) or _clean_text(record.host_id)).lower()


def _is_superseded_local_supervisor_record(record: "SupervisorFleetRecord", records: list["SupervisorFleetRecord"] | None) -> bool:
    if not records or not _is_local_supervisor_record(record):
        return False
    if _freshness_state(record.last_seen_at) != "offline":
        return False
    host_key = _local_supervisor_host_key(record)
    if not host_key:
        return False
    anchor = _record_age_anchor(record)
    if anchor is None:
        return False
    for other in records:
        if other.supervisor_id == record.supervisor_id:
            continue
        if not _is_local_supervisor_record(other):
            continue
        if _local_supervisor_host_key(other) != host_key:
            continue
        if _freshness_state(other.last_seen_at) in {"offline", "error"}:
            continue
        other_anchor = _record_age_anchor(other)
        if other_anchor is not None and other_anchor > anchor:
            return True
    return False


def _is_historical_supervisor_record(
    record: "SupervisorFleetRecord",
    records: list["SupervisorFleetRecord"] | None = None,
) -> bool:
    if _is_local_supervisor_record(record) and not _is_superseded_local_supervisor_record(record, records):
        return False
    if _freshness_state(record.last_seen_at) != "offline":
        return False
    anchor = _record_age_anchor(record)
    if anchor is None:
        return False
    age_s = max(0.0, (datetime.now(timezone.utc) - anchor).total_seconds())
    return age_s >= _historical_after_s()


def _active_node_runtime_count(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if _clean_text(item.get("freshness_state")).lower() not in {"offline", "error"})


def _default_enrollment_ttl_s() -> int:
    raw = str(os.getenv("HEXE_SUPERVISOR_ENROLLMENT_TTL_S", "900")).strip()
    try:
        return min(max(int(raw), 60), 24 * 60 * 60)
    except Exception:
        return 900


class SupervisorRegistrationRequest(BaseModel):
    supervisor_id: str = Field(..., min_length=1)
    supervisor_name: str | None = None
    supervisor_version: str | None = None
    host_id: str | None = None
    hostname: str | None = None
    api_base_url: str | None = None
    transport: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SupervisorHeartbeatRequest(BaseModel):
    supervisor_id: str = Field(..., min_length=1)
    supervisor_name: str | None = None
    supervisor_version: str | None = None
    host_id: str | None = None
    hostname: str | None = None
    api_base_url: str | None = None
    transport: str | None = None
    health_status: str | None = None
    lifecycle_state: str | None = None
    resources: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    managed_node_count: int | None = None
    registered_runtime_count: int | None = None
    core_runtime_count: int | None = None
    registered_runtimes: list[dict[str, Any]] = Field(default_factory=list)
    core_runtimes: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SupervisorCoreRuntimeReportRequest(BaseModel):
    supervisor_id: str = Field(..., min_length=1)
    core_runtimes: list[dict[str, Any]] = Field(default_factory=list)


class SupervisorUpdateStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_mode: Literal["git", "core_host"] = "git"
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    service_update: bool = False


class SupervisorEnrollmentTokenCreateRequest(BaseModel):
    supervisor_id: str | None = None
    supervisor_name: str | None = None
    ttl_seconds: int | None = Field(default=None, ge=60, le=24 * 60 * 60)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SupervisorEnrollmentRequest(SupervisorRegistrationRequest):
    enrollment_token: str = Field(..., min_length=16)


@dataclass
class SupervisorFleetRecord:
    supervisor_id: str
    supervisor_name: str
    supervisor_version: str | None
    host_id: str | None
    hostname: str | None
    api_base_url: str | None
    transport: str | None
    trust_status: str
    health_status: str
    lifecycle_state: str
    capabilities: list[str]
    resources: dict[str, Any]
    runtime: dict[str, Any]
    managed_node_count: int | None
    registered_runtime_count: int | None
    core_runtime_count: int | None
    registered_runtimes: list[dict[str, Any]]
    core_runtimes: list[dict[str, Any]]
    metadata: dict[str, Any]
    first_seen_at: str
    last_seen_at: str | None
    updated_at: str
    reporting_token_hash: str | None = None
    schema_version: str = SUPERVISOR_REGISTRY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "supervisor_id": self.supervisor_id,
            "supervisor_name": self.supervisor_name,
            "supervisor_version": self.supervisor_version,
            "host_id": self.host_id,
            "hostname": self.hostname,
            "api_base_url": self.api_base_url,
            "transport": self.transport,
            "trust_status": self.trust_status,
            "health_status": self.health_status,
            "lifecycle_state": self.lifecycle_state,
            "capabilities": list(self.capabilities or []),
            "resources": dict(self.resources or {}),
            "runtime": dict(self.runtime or {}),
            "managed_node_count": self.managed_node_count,
            "registered_runtime_count": self.registered_runtime_count,
            "core_runtime_count": self.core_runtime_count,
            "registered_runtimes": [dict(item or {}) for item in self.registered_runtimes or []],
            "core_runtimes": [dict(item or {}) for item in self.core_runtimes or []],
            "metadata": dict(self.metadata or {}),
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "updated_at": self.updated_at,
            "reporting_token_hash": self.reporting_token_hash,
        }

    def to_api_dict(self, *, visibility_state: str | None = None) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("reporting_token_hash", None)
        payload["freshness_state"] = _freshness_state(self.last_seen_at)
        payload["visibility_state"] = visibility_state or ("historical" if _is_historical_supervisor_record(self) else "active")
        payload["freshness_age_s"] = _freshness_age_s(self.last_seen_at)
        payload["freshness_reason"] = _freshness_reason(self)
        return payload


@dataclass
class SupervisorEnrollmentTokenRecord:
    token_id: str
    token_hash: str
    supervisor_id: str | None
    supervisor_name: str | None
    created_at: str
    expires_at: str
    consumed_at: str | None = None
    consumed_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SUPERVISOR_ENROLLMENT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "token_id": self.token_id,
            "token_hash": self.token_hash,
            "supervisor_id": self.supervisor_id,
            "supervisor_name": self.supervisor_name,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "consumed_at": self.consumed_at,
            "consumed_by": self.consumed_by,
            "metadata": dict(self.metadata or {}),
        }

    def to_api_dict(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("token_hash", None)
        return payload


class SupervisorFleetStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_repo_root() / "data" / "supervisor_registrations.json")
        self._records: dict[str, SupervisorFleetRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        items = raw.get("items") if isinstance(raw, dict) and isinstance(raw.get("items"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            supervisor_id = _clean_text(item.get("supervisor_id"))
            if not supervisor_id:
                continue
            first_seen_at = _clean_text(item.get("first_seen_at"), _utcnow_iso())
            updated_at = _clean_text(item.get("updated_at"), first_seen_at)
            record = SupervisorFleetRecord(
                supervisor_id=supervisor_id,
                supervisor_name=_clean_text(item.get("supervisor_name"), supervisor_id),
                supervisor_version=_clean_text(item.get("supervisor_version")) or None,
                host_id=_clean_text(item.get("host_id")) or None,
                hostname=_clean_text(item.get("hostname")) or None,
                api_base_url=_clean_text(item.get("api_base_url")) or None,
                transport=_clean_text(item.get("transport")) or None,
                trust_status=_clean_text(item.get("trust_status"), "trusted"),
                health_status=_clean_text(item.get("health_status"), "unknown"),
                lifecycle_state=_clean_text(item.get("lifecycle_state"), "unknown"),
                capabilities=[_clean_text(value) for value in item.get("capabilities", []) if _clean_text(value)]
                if isinstance(item.get("capabilities"), list)
                else [],
                resources=dict(item.get("resources") or {}) if isinstance(item.get("resources"), dict) else {},
                runtime=dict(item.get("runtime") or {}) if isinstance(item.get("runtime"), dict) else {},
                managed_node_count=item.get("managed_node_count") if isinstance(item.get("managed_node_count"), int) else None,
                registered_runtime_count=(
                    item.get("registered_runtime_count") if isinstance(item.get("registered_runtime_count"), int) else None
                ),
                core_runtime_count=item.get("core_runtime_count") if isinstance(item.get("core_runtime_count"), int) else None,
                registered_runtimes=[
                    dict(value) for value in item.get("registered_runtimes", []) if isinstance(value, dict)
                ]
                if isinstance(item.get("registered_runtimes"), list)
                else [],
                core_runtimes=[dict(value) for value in item.get("core_runtimes", []) if isinstance(value, dict)]
                if isinstance(item.get("core_runtimes"), list)
                else [],
                metadata=dict(item.get("metadata") or {}) if isinstance(item.get("metadata"), dict) else {},
                first_seen_at=first_seen_at,
                last_seen_at=_clean_text(item.get("last_seen_at")) or None,
                updated_at=updated_at,
                reporting_token_hash=_clean_text(item.get("reporting_token_hash")) or None,
                schema_version=_clean_text(item.get("schema_version"), SUPERVISOR_REGISTRY_SCHEMA_VERSION),
            )
            self._records[supervisor_id] = record

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SUPERVISOR_REGISTRY_SCHEMA_VERSION,
            "items": [record.to_dict() for record in sorted(self._records.values(), key=lambda item: item.supervisor_id)],
        }
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def list(self, *, include_historical: bool = False) -> list[SupervisorFleetRecord]:
        records = sorted(self._records.values(), key=self._list_sort_key)
        if include_historical:
            return records
        return [record for record in records if not self.is_historical(record)]

    def historical_count(self) -> int:
        return sum(1 for record in self._records.values() if self.is_historical(record))

    def is_historical(self, record: SupervisorFleetRecord) -> bool:
        return _is_historical_supervisor_record(record, records=list(self._records.values()))

    def api_dict(self, record: SupervisorFleetRecord) -> dict[str, Any]:
        visibility_state = "historical" if self.is_historical(record) else "active"
        visibility_reason = (
            "superseded_local_supervisor"
            if _is_superseded_local_supervisor_record(record, list(self._records.values()))
            else None
        )
        payload = record.to_api_dict(visibility_state=visibility_state)
        payload["visibility_reason"] = visibility_reason
        payload["freshness_reason"] = _freshness_reason(record, visibility_reason=visibility_reason)
        return payload

    @staticmethod
    def _list_sort_key(record: SupervisorFleetRecord) -> tuple[int, str]:
        attached_to_core = bool((record.metadata or {}).get("attached_to_core"))
        is_local = attached_to_core or _clean_text(record.transport).lower() == "local"
        return (0 if is_local else 1, record.supervisor_id)

    def get(self, supervisor_id: str) -> SupervisorFleetRecord | None:
        return self._records.get(_clean_text(supervisor_id))

    def delete(self, supervisor_id: str) -> SupervisorFleetRecord | None:
        key = _clean_text(supervisor_id)
        if not key:
            return None
        record = self._records.pop(key, None)
        if record is not None:
            self._save()
        return record

    def register(self, body: SupervisorRegistrationRequest) -> SupervisorFleetRecord:
        now = _utcnow_iso()
        existing = self.get(body.supervisor_id)
        record = SupervisorFleetRecord(
            supervisor_id=_clean_text(body.supervisor_id),
            supervisor_name=_clean_text(body.supervisor_name, body.supervisor_id),
            supervisor_version=_clean_text(body.supervisor_version) or (existing.supervisor_version if existing else None),
            host_id=_clean_text(body.host_id) or (existing.host_id if existing else None),
            hostname=_clean_text(body.hostname) or (existing.hostname if existing else None),
            api_base_url=_clean_text(body.api_base_url) or (existing.api_base_url if existing else None),
            transport=_clean_text(body.transport) or (existing.transport if existing else None),
            trust_status="trusted",
            health_status=existing.health_status if existing else "registered",
            lifecycle_state=existing.lifecycle_state if existing else "unknown",
            capabilities=[_clean_text(value) for value in body.capabilities if _clean_text(value)]
            or (existing.capabilities if existing else []),
            resources=existing.resources if existing else {},
            runtime=existing.runtime if existing else {},
            managed_node_count=existing.managed_node_count if existing else None,
            registered_runtime_count=existing.registered_runtime_count if existing else None,
            core_runtime_count=existing.core_runtime_count if existing else None,
            registered_runtimes=existing.registered_runtimes if existing else [],
            core_runtimes=existing.core_runtimes if existing else [],
            metadata=dict(body.metadata or {}) or (existing.metadata if existing else {}),
            first_seen_at=existing.first_seen_at if existing else now,
            last_seen_at=existing.last_seen_at if existing else None,
            updated_at=now,
            reporting_token_hash=existing.reporting_token_hash if existing else None,
        )
        self._records[record.supervisor_id] = record
        self._save()
        return record

    def heartbeat(self, body: SupervisorHeartbeatRequest) -> SupervisorFleetRecord:
        now = _utcnow_iso()
        existing = self.get(body.supervisor_id)
        base = existing or self.register(
            SupervisorRegistrationRequest(
                supervisor_id=body.supervisor_id,
                supervisor_name=body.supervisor_name,
                supervisor_version=body.supervisor_version,
                host_id=body.host_id,
                hostname=body.hostname,
                api_base_url=body.api_base_url,
                transport=body.transport,
                capabilities=body.capabilities,
                metadata=body.metadata,
            )
        )
        record = SupervisorFleetRecord(
            supervisor_id=base.supervisor_id,
            supervisor_name=_clean_text(body.supervisor_name, base.supervisor_name),
            supervisor_version=_clean_text(body.supervisor_version) or base.supervisor_version,
            host_id=_clean_text(body.host_id) or base.host_id,
            hostname=_clean_text(body.hostname) or base.hostname,
            api_base_url=_clean_text(body.api_base_url) or base.api_base_url,
            transport=_clean_text(body.transport) or base.transport,
            trust_status=base.trust_status,
            health_status=_clean_text(body.health_status, base.health_status),
            lifecycle_state=_clean_text(body.lifecycle_state, base.lifecycle_state),
            capabilities=[_clean_text(value) for value in body.capabilities if _clean_text(value)] or base.capabilities,
            resources=dict(body.resources or {}),
            runtime=dict(body.runtime or {}),
            managed_node_count=body.managed_node_count,
            registered_runtime_count=body.registered_runtime_count,
            core_runtime_count=body.core_runtime_count,
            registered_runtimes=[dict(item) for item in body.registered_runtimes if isinstance(item, dict)],
            core_runtimes=[dict(item) for item in body.core_runtimes if isinstance(item, dict)],
            metadata={**dict(base.metadata or {}), **dict(body.metadata or {})},
            first_seen_at=base.first_seen_at,
            last_seen_at=now,
            updated_at=now,
            reporting_token_hash=base.reporting_token_hash,
        )
        self._records[record.supervisor_id] = record
        self._save()
        return record

    def update_core_runtimes(self, supervisor_id: str, core_runtimes: list[dict[str, Any]]) -> SupervisorFleetRecord:
        record = self.get(supervisor_id)
        if record is None:
            raise HTTPException(status_code=404, detail="supervisor_not_found")
        now = _utcnow_iso()
        record.core_runtimes = [dict(item) for item in core_runtimes if isinstance(item, dict)]
        record.core_runtime_count = len(record.core_runtimes)
        record.metadata = {**dict(record.metadata or {}), "local_core_runtime_report": True}
        record.updated_at = now
        record.last_seen_at = record.last_seen_at or now
        self._records[record.supervisor_id] = record
        self._save()
        return record

    def set_reporting_token(self, supervisor_id: str, token: str) -> SupervisorFleetRecord:
        record = self.get(supervisor_id)
        if record is None:
            raise HTTPException(status_code=404, detail="supervisor_not_found")
        record.reporting_token_hash = _sha256_text(token)
        record.updated_at = _utcnow_iso()
        self._records[record.supervisor_id] = record
        self._save()
        return record

    def set_update_status(self, supervisor_id: str, update_status: dict[str, Any]) -> SupervisorFleetRecord:
        record = self.get(supervisor_id)
        if record is None:
            raise HTTPException(status_code=404, detail="supervisor_not_found")
        record.metadata = {**dict(record.metadata or {}), "update_status": _sanitize_update_payload(update_status)}
        record.updated_at = _utcnow_iso()
        self._records[record.supervisor_id] = record
        self._save()
        return record

    def set_auto_update_decision(self, supervisor_id: str, decision: dict[str, Any]) -> SupervisorFleetRecord:
        record = self.get(supervisor_id)
        if record is None:
            raise HTTPException(status_code=404, detail="supervisor_not_found")
        record.metadata = {**dict(record.metadata or {}), "auto_update_decision": _sanitize_update_payload(decision)}
        record.updated_at = _utcnow_iso()
        self._records[record.supervisor_id] = record
        self._save()
        return record

    def set_version_audit_status(
        self,
        supervisor_id: str,
        version_audit: dict[str, Any],
        *,
        update_status: dict[str, Any] | None = None,
        local_source_gate: dict[str, Any] | None = None,
        supervisor_version: str | None = None,
    ) -> SupervisorFleetRecord:
        record = self.get(supervisor_id)
        if record is None:
            raise HTTPException(status_code=404, detail="supervisor_not_found")
        metadata = {**dict(record.metadata or {}), "version_audit": _sanitize_update_payload(version_audit)}
        if update_status is not None:
            metadata["update_status"] = _sanitize_update_payload(update_status)
        if local_source_gate is not None:
            metadata["local_source_gate"] = _sanitize_update_payload(local_source_gate)
        record.metadata = metadata
        if _clean_text(supervisor_version):
            record.supervisor_version = _clean_text(supervisor_version)
        record.updated_at = _utcnow_iso()
        self._records[record.supervisor_id] = record
        self._save()
        return record

    def verify_reporting_token(self, supervisor_id: str, token: str | None) -> bool:
        if not token:
            return False
        record = self.get(supervisor_id)
        expected = record.reporting_token_hash if record else None
        if not expected:
            return False
        return hmac.compare_digest(expected, _sha256_text(token))


class SupervisorEnrollmentTokenStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_repo_root() / "data" / "supervisor_enrollment_tokens.json")
        self._records: dict[str, SupervisorEnrollmentTokenRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        items = raw.get("items") if isinstance(raw, dict) and isinstance(raw.get("items"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            token_id = _clean_text(item.get("token_id"))
            token_hash = _clean_text(item.get("token_hash"))
            if not token_id or not token_hash:
                continue
            self._records[token_id] = SupervisorEnrollmentTokenRecord(
                token_id=token_id,
                token_hash=token_hash,
                supervisor_id=_clean_text(item.get("supervisor_id")) or None,
                supervisor_name=_clean_text(item.get("supervisor_name")) or None,
                created_at=_clean_text(item.get("created_at"), _utcnow_iso()),
                expires_at=_clean_text(item.get("expires_at"), _utcnow_iso()),
                consumed_at=_clean_text(item.get("consumed_at")) or None,
                consumed_by=_clean_text(item.get("consumed_by")) or None,
                metadata=dict(item.get("metadata") or {}) if isinstance(item.get("metadata"), dict) else {},
                schema_version=_clean_text(item.get("schema_version"), SUPERVISOR_ENROLLMENT_SCHEMA_VERSION),
            )

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SUPERVISOR_ENROLLMENT_SCHEMA_VERSION,
            "items": [record.to_dict() for record in sorted(self._records.values(), key=lambda item: item.token_id)],
        }
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def create(self, body: SupervisorEnrollmentTokenCreateRequest) -> tuple[SupervisorEnrollmentTokenRecord, str]:
        now = datetime.now(timezone.utc)
        ttl_s = body.ttl_seconds or _default_enrollment_ttl_s()
        raw_token = f"hexe_sup_enroll_{secrets.token_urlsafe(32)}"
        record = SupervisorEnrollmentTokenRecord(
            token_id=secrets.token_urlsafe(12),
            token_hash=_sha256_text(raw_token),
            supervisor_id=_clean_text(body.supervisor_id) or None,
            supervisor_name=_clean_text(body.supervisor_name) or None,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=ttl_s)).isoformat(),
            metadata=dict(body.metadata or {}),
        )
        self._records[record.token_id] = record
        self._save()
        return record, raw_token

    def consume(self, token: str, *, supervisor_id: str) -> SupervisorEnrollmentTokenRecord:
        token_hash = _sha256_text(_clean_text(token))
        matched: SupervisorEnrollmentTokenRecord | None = None
        for record in self._records.values():
            if hmac.compare_digest(record.token_hash, token_hash):
                matched = record
                break
        if matched is None:
            raise HTTPException(status_code=401, detail="invalid_enrollment_token")
        if matched.consumed_at:
            raise HTTPException(status_code=409, detail="enrollment_token_already_used")
        expires_at = _parse_iso(matched.expires_at)
        if expires_at is not None and expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="enrollment_token_expired")
        expected_supervisor_id = _clean_text(matched.supervisor_id)
        actual_supervisor_id = _clean_text(supervisor_id)
        if expected_supervisor_id and expected_supervisor_id != actual_supervisor_id:
            raise HTTPException(status_code=403, detail="enrollment_token_supervisor_mismatch")
        matched.consumed_at = _utcnow_iso()
        matched.consumed_by = actual_supervisor_id
        self._records[matched.token_id] = matched
        self._save()
        return matched


def build_supervisors_router(
    store: SupervisorFleetStore | None = None,
    enrollment_store: SupervisorEnrollmentTokenStore | None = None,
    audit_store: Any | None = None,
) -> APIRouter:
    router = APIRouter()
    registry = store or SupervisorFleetStore()
    enrollment_registry = enrollment_store or SupervisorEnrollmentTokenStore()

    def authorize_report(
        *,
        supervisor_id: str,
        request: Request,
        x_admin_token: str | None,
        x_supervisor_token: str | None,
    ) -> None:
        if x_admin_token:
            require_admin_token(x_admin_token, request)
            return
        if x_supervisor_token:
            if registry.verify_reporting_token(supervisor_id, x_supervisor_token):
                return
            raise HTTPException(status_code=401, detail="invalid_supervisor_token")
        require_admin_token(x_admin_token, request)

    def record_update_audit(event_type: str, *, supervisor_id: str, status: str, details: dict[str, Any] | None = None) -> None:
        if audit_store is None:
            return
        record_sync = getattr(audit_store, "record_sync", None)
        if not callable(record_sync):
            return
        record_sync(
            event_type=event_type,
            actor_role="admin",
            actor_id="admin",
            details=_sanitize_update_payload(
                {
                    "supervisor_id": supervisor_id,
                    "status": status,
                    **dict(details or {}),
                }
            ),
        )

    def sync_local_supervisor(request: Request) -> None:
        cache = getattr(request.app.state, "supervisor_fleet_local_sync_cache", None)
        if not isinstance(cache, dict):
            cache = {"updated_at": 0.0}
            setattr(request.app.state, "supervisor_fleet_local_sync_cache", cache)
        now = time.time()
        cached_at = cache.get("updated_at")
        if isinstance(cached_at, (int, float)) and now - cached_at < _local_probe_cache_s():
            return

        client = getattr(request.app.state, "supervisor_client", None)
        request_json = getattr(client, "request_json", None)
        if not callable(request_json):
            return

        health = request_json("GET", "/api/supervisor/health")
        runtime = request_json("GET", "/api/supervisor/runtime")
        info = request_json("GET", "/api/supervisor/info")
        runtimes = request_json("GET", "/api/supervisor/runtimes")
        core_runtimes = request_json("GET", "/api/supervisor/core/runtimes")
        if not any(isinstance(item, dict) for item in (health, runtime, info, runtimes, core_runtimes)):
            return

        info_payload = _dict_payload(info)
        health_payload = _dict_payload(health)
        runtime_payload = _dict_payload(runtime)
        host = (
            _dict_payload(info_payload.get("host"))
            or _dict_payload(health_payload.get("host"))
            or _dict_payload(runtime_payload.get("host"))
        )
        resources = (
            _dict_payload(health_payload.get("resources"))
            or _dict_payload(info_payload.get("resources"))
            or _dict_payload(runtime_payload.get("resources"))
        )
        managed_nodes = _list_payload(runtime_payload.get("managed_nodes")) or _list_payload(info_payload.get("managed_nodes"))
        supervisor_id = (
            _clean_text(info_payload.get("supervisor_id"))
            or _clean_text(host.get("host_id"))
            or _clean_text(host.get("hostname"))
        )
        if not supervisor_id:
            return

        existing = registry.get(supervisor_id)
        node_runtimes = (
            _list_payload(_dict_payload(runtimes).get("items"))
            if isinstance(runtimes, dict)
            else list(existing.registered_runtimes if existing else [])
        )
        core_runtime_items = (
            _list_payload(_dict_payload(core_runtimes).get("items"))
            if isinstance(core_runtimes, dict)
            else list(existing.core_runtimes if existing else [])
        )
        core_runtime_items = _with_local_core_runtime_telemetry(core_runtime_items, request)
        managed_node_count = _active_node_runtime_count(node_runtimes) if node_runtimes else (
            len(managed_nodes) if managed_nodes else existing.managed_node_count if existing else 0
        )
        registry.heartbeat(
            SupervisorHeartbeatRequest(
                supervisor_id=supervisor_id,
                supervisor_name=existing.supervisor_name if existing else supervisor_id,
                supervisor_version=existing.supervisor_version if existing else None,
                host_id=_clean_text(host.get("host_id")) or None,
                hostname=_clean_text(host.get("hostname")) or None,
                api_base_url=existing.api_base_url if existing else None,
                transport="local",
                health_status=_clean_text(health_payload.get("status"), "ok"),
                lifecycle_state="running",
                resources=resources,
                runtime=runtime_payload,
                managed_node_count=managed_node_count,
                registered_runtime_count=len(node_runtimes),
                core_runtime_count=len(core_runtime_items),
                registered_runtimes=node_runtimes,
                core_runtimes=core_runtime_items,
                capabilities=_supervisor_capabilities(resources, local_core_attached=True),
                metadata=_supervisor_metadata(resources, reporter="core-local-supervisor-probe", attached_to_core=True),
            )
        )
        cache["updated_at"] = now

    def request_supervisor_history(
        record: SupervisorFleetRecord,
        request: Request,
        path: str,
        *,
        range_value: str,
        step_value: str | None,
    ) -> dict[str, Any]:
        params = _history_params(range_value, step_value)
        if _is_local_supervisor_record(record):
            client = getattr(request.app.state, "supervisor_client", None)
            request_json = getattr(client, "request_json", None)
            if not callable(request_json):
                raise HTTPException(status_code=503, detail="supervisor_client_unavailable")
            payload = request_json("GET", path, params=params)
            if payload is None:
                raise HTTPException(status_code=502, detail="supervisor_unavailable")
            return payload

        base_url = _clean_text(record.api_base_url).rstrip("/")
        if not base_url:
            raise HTTPException(status_code=409, detail="supervisor_api_base_url_missing")
        try:
            response = httpx.get(f"{base_url}{path}", params=params, timeout=_supervisor_history_timeout_s())
        except httpx.HTTPError:
            raise HTTPException(status_code=502, detail="supervisor_unavailable") from None
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="supervisor_history_not_found")
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="supervisor_history_error")
        try:
            payload = response.json()
        except ValueError:
            raise HTTPException(status_code=502, detail="supervisor_history_invalid_json") from None
        if not isinstance(payload, dict):
            raise HTTPException(status_code=502, detail="supervisor_history_invalid_payload")
        return payload

    def require_updateable_supervisor(record: SupervisorFleetRecord) -> None:
        freshness = _freshness_state(record.last_seen_at)
        if freshness != "online":
            raise HTTPException(
                status_code=409,
                detail={"error": "supervisor_not_online", "freshness_state": freshness},
            )

    def request_supervisor_update_api(
        record: SupervisorFleetRecord,
        request: Request,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if _is_local_supervisor_record(record):
            client = getattr(request.app.state, "supervisor_client", None)
            request_json = getattr(client, "request_json", None)
            if not callable(request_json):
                raise HTTPException(status_code=503, detail={"error": "supervisor_client_unavailable"})
            result = request_json(method, path, payload=payload)
            if result is None:
                raise HTTPException(status_code=502, detail={"error": "supervisor_update_api_unavailable"})
            if not isinstance(result, dict):
                raise HTTPException(status_code=502, detail={"error": "supervisor_update_api_invalid_payload"})
            return result

        base_url = _clean_text(record.api_base_url).rstrip("/")
        if not base_url:
            raise HTTPException(status_code=409, detail={"error": "supervisor_api_base_url_missing"})
        try:
            response = httpx.request(method.upper(), f"{base_url}{path}", json=payload, timeout=_supervisor_history_timeout_s())
        except httpx.HTTPError:
            raise HTTPException(status_code=502, detail={"error": "supervisor_update_api_unavailable"}) from None
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail={"error": "supervisor_update_api_not_found"})
        if response.status_code >= 400:
            try:
                detail = response.json()
            except ValueError:
                detail = {"error": "supervisor_update_api_error", "status_code": response.status_code}
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "supervisor_update_api_error",
                    "status_code": response.status_code,
                    "supervisor_detail": _sanitize_update_payload(detail),
                },
            )
        try:
            result = response.json()
        except ValueError:
            raise HTTPException(status_code=502, detail={"error": "supervisor_update_api_invalid_json"}) from None
        if not isinstance(result, dict):
            raise HTTPException(status_code=502, detail={"error": "supervisor_update_api_invalid_payload"})
        return result

    def update_status_for_record(record: SupervisorFleetRecord, request: Request) -> dict[str, Any]:
        require_updateable_supervisor(record)
        payload = request_supervisor_update_api(record, request, "GET", "/api/supervisor/update/status")
        if not isinstance(payload.get("supported_modes", []), list):
            raise HTTPException(status_code=502, detail={"error": "supervisor_update_status_invalid_payload"})
        registry.set_update_status(record.supervisor_id, payload)
        record_update_audit(
            "supervisor_update_status_checked",
            supervisor_id=record.supervisor_id,
            status="success",
            details={"source": "core", "update_state": payload.get("update_state")},
        )
        return _sanitize_update_payload(payload)

    def build_core_host_update_payload(record: SupervisorFleetRecord, body: SupervisorUpdateStartRequest) -> dict[str, Any]:
        source_root = _supervisor_package_source_root()
        try:
            package = build_supervisor_update_package(
                source_root,
                source_version=supervisor_reported_version(source_root) or _clean_text(os.getenv("HEXE_CORE_VERSION")) or None,
                commit_sha=_source_commit_sha(),
                compatibility={
                    "target_supervisor_id": record.supervisor_id,
                    "target_supervisor_version": record.supervisor_version,
                    "source": "core_host",
                },
            )
        except SupervisorUpdatePackageError as exc:
            raise HTTPException(
                status_code=409,
                detail={"error": "supervisor_update_package_build_failed", "message": str(exc), "source_root": str(source_root)},
            ) from None
        except Exception:
            raise HTTPException(
                status_code=500,
                detail={"error": "supervisor_update_package_build_failed", "source_root": str(source_root)},
            ) from None
        return {
            "source_mode": "core_host",
            "idempotency_key": body.idempotency_key,
            "service_update": body.service_update,
            **package.to_request_payload(),
        }

    @router.get("/supervisors")
    def list_supervisors(
        request: Request,
        include_historical: bool = Query(default=False),
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        sync_local_supervisor(request)
        return {
            "items": [registry.api_dict(record) for record in registry.list(include_historical=include_historical)],
            "hidden_historical_count": 0 if include_historical else registry.historical_count(),
        }

    @router.post("/supervisors/enrollment-tokens")
    def create_supervisor_enrollment_token(
        body: SupervisorEnrollmentTokenCreateRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        record, token = enrollment_registry.create(body)
        return {"ok": True, "enrollment_token": token, "one_time_token": token, "token": record.to_api_dict()}

    @router.post("/supervisors/enroll")
    def enroll_supervisor(body: SupervisorEnrollmentRequest) -> dict[str, Any]:
        enrollment_registry.consume(body.enrollment_token, supervisor_id=body.supervisor_id)
        reporting_token = f"hexe_sup_report_{secrets.token_urlsafe(32)}"
        record = registry.register(
            SupervisorRegistrationRequest(
                supervisor_id=body.supervisor_id,
                supervisor_name=body.supervisor_name,
                supervisor_version=body.supervisor_version,
                host_id=body.host_id,
                hostname=body.hostname,
                api_base_url=body.api_base_url,
                transport=body.transport,
                capabilities=body.capabilities,
                metadata=body.metadata,
            )
        )
        record = registry.set_reporting_token(record.supervisor_id, reporting_token)
        return {
            "ok": True,
            "supervisor": registry.api_dict(record),
            "reporting_token": reporting_token,
            "token_type": "supervisor-reporting",
        }

    @router.get("/supervisors/{supervisor_id}")
    def get_supervisor(
        supervisor_id: str,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        sync_local_supervisor(request)
        record = registry.get(supervisor_id)
        if record is None:
            raise HTTPException(status_code=404, detail="supervisor_not_found")
        return {"supervisor": registry.api_dict(record)}

    @router.get("/supervisors/{supervisor_id}/update/status")
    def get_supervisor_update_status(
        supervisor_id: str,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        sync_local_supervisor(request)
        record = registry.get(supervisor_id)
        if record is None:
            raise HTTPException(status_code=404, detail="supervisor_not_found")
        try:
            status = update_status_for_record(record, request)
        except HTTPException as exc:
            record_update_audit(
                "supervisor_update_status_failed",
                supervisor_id=supervisor_id,
                status="failed",
                details={"detail": exc.detail},
            )
            raise
        return {"ok": True, "supervisor_id": record.supervisor_id, "update_status": status}

    @router.post("/supervisors/{supervisor_id}/update/start")
    def start_supervisor_update(
        supervisor_id: str,
        body: SupervisorUpdateStartRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        sync_local_supervisor(request)
        record = registry.get(supervisor_id)
        if record is None:
            raise HTTPException(status_code=404, detail="supervisor_not_found")
        try:
            status = update_status_for_record(record, request)
            supported_modes = status.get("supported_modes") if isinstance(status.get("supported_modes"), list) else []
            if body.source_mode not in supported_modes:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "supervisor_update_mode_unsupported",
                        "mode": body.source_mode,
                        "reason": dict(status.get("unsupported_reasons") or {}).get(body.source_mode)
                        if isinstance(status.get("unsupported_reasons"), dict)
                        else None,
                    },
                )
            payload = (
                build_core_host_update_payload(record, body)
                if body.source_mode == "core_host"
                else body.model_dump(mode="json")
            )
            result = request_supervisor_update_api(record, request, "POST", "/api/supervisor/update/start", payload=payload)
            registry.set_update_status(record.supervisor_id, dict(result.get("status") or result))
            record_update_audit(
                "supervisor_update_requested",
                supervisor_id=record.supervisor_id,
                status="accepted" if bool(result.get("accepted")) else "replayed",
                details={
                    "source_mode": body.source_mode,
                    "idempotency_key": body.idempotency_key,
                    "package_id": payload.get("package_id") if body.source_mode == "core_host" else None,
                    "result": result,
                },
            )
        except HTTPException as exc:
            record_update_audit(
                "supervisor_update_rejected",
                supervisor_id=supervisor_id,
                status="failed",
                details={
                    "source_mode": body.source_mode,
                    "idempotency_key": body.idempotency_key,
                    "detail": exc.detail,
                },
            )
            raise
        return {"ok": True, "supervisor_id": record.supervisor_id, "result": _sanitize_update_payload(result)}

    @router.get("/supervisors/{supervisor_id}/resources/history")
    def get_supervisor_resource_history(
        supervisor_id: str,
        request: Request,
        range: str = "24h",  # noqa: A002
        step: str | None = "60s",
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        sync_local_supervisor(request)
        record = registry.get(supervisor_id)
        if record is None:
            raise HTTPException(status_code=404, detail="supervisor_not_found")
        return request_supervisor_history(
            record,
            request,
            "/api/supervisor/resources/history",
            range_value=range,
            step_value=step,
        )

    @router.get("/supervisors/{supervisor_id}/runtimes/{node_id}/resources/history")
    def get_supervisor_runtime_resource_history(
        supervisor_id: str,
        node_id: str,
        request: Request,
        range: str = "24h",  # noqa: A002
        step: str | None = "60s",
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        sync_local_supervisor(request)
        record = registry.get(supervisor_id)
        if record is None:
            raise HTTPException(status_code=404, detail="supervisor_not_found")
        return request_supervisor_history(
            record,
            request,
            f"/api/supervisor/runtimes/{node_id}/resources/history",
            range_value=range,
            step_value=step,
        )

    @router.get("/supervisors/{supervisor_id}/core/runtimes/{runtime_id}/resources/history")
    def get_supervisor_core_runtime_resource_history(
        supervisor_id: str,
        runtime_id: str,
        request: Request,
        range: str = "24h",  # noqa: A002
        step: str | None = "60s",
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        sync_local_supervisor(request)
        record = registry.get(supervisor_id)
        if record is None:
            raise HTTPException(status_code=404, detail="supervisor_not_found")
        return request_supervisor_history(
            record,
            request,
            f"/api/supervisor/core/runtimes/{runtime_id}/resources/history",
            range_value=range,
            step_value=step,
        )

    @router.post("/supervisors/register")
    def register_supervisor(
        body: SupervisorRegistrationRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
        x_supervisor_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        authorize_report(
            supervisor_id=body.supervisor_id,
            request=request,
            x_admin_token=x_admin_token,
            x_supervisor_token=x_supervisor_token,
        )
        record = registry.register(body)
        return {"ok": True, "supervisor": registry.api_dict(record)}

    @router.post("/supervisors/heartbeat")
    def heartbeat_supervisor(
        body: SupervisorHeartbeatRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
        x_supervisor_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        authorize_report(
            supervisor_id=body.supervisor_id,
            request=request,
            x_admin_token=x_admin_token,
            x_supervisor_token=x_supervisor_token,
        )
        record = registry.heartbeat(body)
        return {"ok": True, "supervisor": registry.api_dict(record)}

    @router.post("/supervisors/local/core-runtimes")
    def report_local_core_runtimes(
        body: SupervisorCoreRuntimeReportRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
        x_supervisor_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        authorize_report(
            supervisor_id=body.supervisor_id,
            request=request,
            x_admin_token=x_admin_token,
            x_supervisor_token=x_supervisor_token,
        )
        record = registry.update_core_runtimes(body.supervisor_id, body.core_runtimes)
        return {"ok": True, "supervisor": registry.api_dict(record)}

    @router.delete("/supervisors/{supervisor_id}")
    def delete_supervisor(
        supervisor_id: str,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        record = registry.delete(supervisor_id)
        if record is None:
            raise HTTPException(status_code=404, detail="supervisor_not_found")
        return {"ok": True, "deleted": record.to_api_dict()}

    return router
