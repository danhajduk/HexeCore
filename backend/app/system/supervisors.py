from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.admin import require_admin_token

SUPERVISOR_REGISTRY_SCHEMA_VERSION = "1"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


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
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    metadata: dict[str, Any]
    first_seen_at: str
    last_seen_at: str | None
    updated_at: str
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
            "metadata": dict(self.metadata or {}),
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "updated_at": self.updated_at,
        }

    def to_api_dict(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload["freshness_state"] = _freshness_state(self.last_seen_at)
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
                metadata=dict(item.get("metadata") or {}) if isinstance(item.get("metadata"), dict) else {},
                first_seen_at=first_seen_at,
                last_seen_at=_clean_text(item.get("last_seen_at")) or None,
                updated_at=updated_at,
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

    def list(self) -> list[SupervisorFleetRecord]:
        return sorted(self._records.values(), key=lambda item: item.supervisor_id)

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
            metadata=dict(body.metadata or {}) or (existing.metadata if existing else {}),
            first_seen_at=existing.first_seen_at if existing else now,
            last_seen_at=existing.last_seen_at if existing else None,
            updated_at=now,
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
            metadata={**dict(base.metadata or {}), **dict(body.metadata or {})},
            first_seen_at=base.first_seen_at,
            last_seen_at=now,
            updated_at=now,
        )
        self._records[record.supervisor_id] = record
        self._save()
        return record


def build_supervisors_router(store: SupervisorFleetStore | None = None) -> APIRouter:
    router = APIRouter()
    registry = store or SupervisorFleetStore()

    @router.get("/supervisors")
    def list_supervisors(request: Request, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        return {"items": [record.to_api_dict() for record in registry.list()]}

    @router.get("/supervisors/{supervisor_id}")
    def get_supervisor(
        supervisor_id: str,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        record = registry.get(supervisor_id)
        if record is None:
            raise HTTPException(status_code=404, detail="supervisor_not_found")
        return {"supervisor": record.to_api_dict()}

    @router.post("/supervisors/register")
    def register_supervisor(
        body: SupervisorRegistrationRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        record = registry.register(body)
        return {"ok": True, "supervisor": record.to_api_dict()}

    @router.post("/supervisors/heartbeat")
    def heartbeat_supervisor(
        body: SupervisorHeartbeatRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        record = registry.heartbeat(body)
        return {"ok": True, "supervisor": record.to_api_dict()}

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
