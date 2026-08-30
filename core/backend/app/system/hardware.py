from __future__ import annotations

import json
import hashlib
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.system.auth.tokens import ServiceTokenError, sign_hs256, validate_claims, verify_hs256

HARDWARE_ACCESS_SCHEMA_VERSION = "1"
HARDWARE_LEASE_AUDIENCE = "hexe.hardware.bluetooth"
SUPPORTED_HARDWARE_RESOURCES = {"bluetooth"}
SUPPORTED_BLUETOOTH_OPERATIONS = {"ble.status", "ble.scan"}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_ts() -> int:
    return int(time.time())


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def clean_text(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def bluetooth_access_policy(value: object | None = None) -> str:
    text = clean_text(value or os.getenv("HEXE_BLUETOOTH_ACCESS_POLICY"), "disabled").lower()
    if text in {"disabled", "ask", "trusted_only", "allowed"}:
        return text
    return "disabled"


def hardware_lease_ttl_s(value: object | None = None) -> int:
    raw = clean_text(value or os.getenv("HEXE_HARDWARE_LEASE_TTL_S"), "600")
    try:
        return min(max(int(float(raw)), 30), 24 * 60 * 60)
    except Exception:
        return 600


def hardware_lease_secret() -> str:
    return clean_text(os.getenv("HEXE_HARDWARE_LEASE_SECRET"))


def freshness_state(record: object) -> str:
    from app.system.supervisors import _freshness_state

    return str(_freshness_state(getattr(record, "last_seen_at", None)))


def supervisor_bluetooth_policy(record: object) -> str:
    metadata = getattr(record, "metadata", {}) if record is not None else {}
    bluetooth = metadata.get("bluetooth") if isinstance(metadata, dict) else None
    policy = bluetooth.get("policy") if isinstance(bluetooth, dict) else None
    return bluetooth_access_policy(policy)


def supervisor_has_bluetooth(record: object) -> bool:
    resources = getattr(record, "resources", {}) if record is not None else {}
    capabilities = getattr(record, "capabilities", []) if record is not None else []
    return bool(
        isinstance(resources, dict)
        and resources.get("bluetooth_present")
        and isinstance(capabilities, list)
        and "bluetooth_governance" in [str(item) for item in capabilities]
    )


def supervisor_broker_url(record: object) -> str | None:
    base = clean_text(getattr(record, "api_base_url", None)).rstrip("/")
    if not base:
        return None
    return f"{base}/api/supervisor/hardware/bluetooth/ble"


def active_bluetooth_supervisors(supervisor_store: object | None) -> list[object]:
    if supervisor_store is None or not hasattr(supervisor_store, "list"):
        return []
    records = supervisor_store.list(include_historical=False)
    return [
        record
        for record in records
        if supervisor_has_bluetooth(record)
        and clean_text(getattr(record, "trust_status", "")).lower() == "trusted"
        and freshness_state(record) == "online"
    ]


class HardwareAccessRequestBody(BaseModel):
    node_id: str = Field(..., min_length=1)
    resource_type: Literal["bluetooth"] = "bluetooth"
    operation: Literal["ble.status", "ble.scan"] = "ble.scan"
    supervisor_id: str | None = None
    adapter: str | None = None
    adapter: str | None = None
    duration_s: int | None = Field(default=None, ge=30, le=24 * 60 * 60)
    reason: str | None = None


class HardwareAccessDecisionBody(BaseModel):
    decision: Literal["approve", "deny"]
    reason: str | None = None
    duration_s: int | None = Field(default=None, ge=30, le=24 * 60 * 60)


class HardwareLeaseReleaseBody(BaseModel):
    node_id: str = Field(..., min_length=1)


class HardwareLeaseValidationBody(BaseModel):
    node_id: str = Field(..., min_length=1)
    lease_token: str = Field(..., min_length=1)
    resource_type: Literal["bluetooth"] = "bluetooth"
    operation: Literal["ble.status", "ble.scan"] = "ble.scan"
    supervisor_id: str | None = None


@dataclass
class HardwareAccessRecord:
    request_id: str
    node_id: str
    resource_type: str
    operation: str
    supervisor_id: str | None
    adapter: str | None
    status: str
    policy: str
    reason: str | None
    created_at: str
    updated_at: str
    decided_at: str | None = None
    decided_by: str | None = None
    decision_reason: str | None = None
    lease_id: str | None = None
    expires_at: str | None = None
    revoked_at: str | None = None
    released_at: str | None = None
    broker_url: str | None = None
    token_hash: str | None = None
    audit: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": HARDWARE_ACCESS_SCHEMA_VERSION,
            "request_id": self.request_id,
            "node_id": self.node_id,
            "resource_type": self.resource_type,
            "operation": self.operation,
            "supervisor_id": self.supervisor_id,
            "adapter": self.adapter,
            "status": self.status,
            "policy": self.policy,
            "reason": self.reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "decision_reason": self.decision_reason,
            "lease_id": self.lease_id,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
            "released_at": self.released_at,
            "broker_url": self.broker_url,
            "token_hash": self.token_hash,
            "audit": [dict(item) for item in self.audit],
        }

    def to_api_dict(self, *, include_token: str | None = None) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("token_hash", None)
        if include_token:
            payload["lease_token"] = include_token
        return payload


class HardwareAccessStore:
    def __init__(self, path: Path | None = None) -> None:
        configured = clean_text(os.getenv("HEXE_HARDWARE_ACCESS_DB"))
        self._path = path or (Path(configured) if configured else repo_root() / "data" / "hardware_access.json")
        self._records: dict[str, HardwareAccessRecord] = {}
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
            request_id = clean_text(item.get("request_id"))
            if not request_id:
                continue
            self._records[request_id] = HardwareAccessRecord(
                request_id=request_id,
                node_id=clean_text(item.get("node_id")),
                resource_type=clean_text(item.get("resource_type"), "bluetooth"),
                operation=clean_text(item.get("operation"), "ble.scan"),
                supervisor_id=clean_text(item.get("supervisor_id")) or None,
                adapter=clean_text(item.get("adapter")) or None,
                status=clean_text(item.get("status"), "pending"),
                policy=clean_text(item.get("policy"), "disabled"),
                reason=clean_text(item.get("reason")) or None,
                created_at=clean_text(item.get("created_at"), utcnow_iso()),
                updated_at=clean_text(item.get("updated_at"), utcnow_iso()),
                decided_at=clean_text(item.get("decided_at")) or None,
                decided_by=clean_text(item.get("decided_by")) or None,
                decision_reason=clean_text(item.get("decision_reason")) or None,
                lease_id=clean_text(item.get("lease_id")) or None,
                expires_at=clean_text(item.get("expires_at")) or None,
                revoked_at=clean_text(item.get("revoked_at")) or None,
                released_at=clean_text(item.get("released_at")) or None,
                broker_url=clean_text(item.get("broker_url")) or None,
                token_hash=clean_text(item.get("token_hash")) or None,
                audit=[dict(row) for row in item.get("audit", []) if isinstance(row, dict)]
                if isinstance(item.get("audit"), list)
                else [],
            )

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": HARDWARE_ACCESS_SCHEMA_VERSION,
            "items": [record.to_dict() for record in sorted(self._records.values(), key=lambda item: item.created_at)],
        }
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def upsert(self, record: HardwareAccessRecord) -> HardwareAccessRecord:
        self._records[record.request_id] = record
        self._save()
        return record

    def get(self, request_id: str) -> HardwareAccessRecord | None:
        return self._records.get(clean_text(request_id))

    def get_by_lease(self, lease_id: str) -> HardwareAccessRecord | None:
        lease_key = clean_text(lease_id)
        if not lease_key:
            return None
        return next((record for record in self._records.values() if record.lease_id == lease_key), None)

    def list(self, *, node_id: str | None = None, status: str | None = None) -> list[HardwareAccessRecord]:
        node_key = clean_text(node_id)
        status_key = clean_text(status).lower()
        records = sorted(self._records.values(), key=lambda item: item.created_at, reverse=True)
        if node_key:
            records = [record for record in records if record.node_id == node_key]
        if status_key:
            records = [record for record in records if record.status == status_key]
        return records


class HardwareAccessService:
    def __init__(self, store: HardwareAccessStore, supervisor_store: object | None) -> None:
        self._store = store
        self._supervisor_store = supervisor_store

    def request_access(self, body: HardwareAccessRequestBody) -> tuple[HardwareAccessRecord, str | None]:
        request_id = f"hwar_{secrets.token_urlsafe(12)}"
        now = utcnow_iso()
        supervisor = self._select_supervisor(body)
        policy = supervisor_bluetooth_policy(supervisor) if supervisor is not None else bluetooth_access_policy()
        status = "pending" if policy == "ask" else "denied"
        token: str | None = None
        record = HardwareAccessRecord(
            request_id=request_id,
            node_id=clean_text(body.node_id),
            resource_type=body.resource_type,
            operation=body.operation,
            supervisor_id=clean_text(getattr(supervisor, "supervisor_id", None)) or None,
            adapter=clean_text(body.adapter) or None,
            status=status,
            policy=policy,
            reason=clean_text(body.reason) or None,
            created_at=now,
            updated_at=now,
            broker_url=supervisor_broker_url(supervisor) if supervisor is not None else None,
            audit=[{"event": "requested", "at": now, "policy": policy}],
        )
        if supervisor is None:
            record.status = "denied"
            record.decision_reason = "bluetooth_supervisor_unavailable"
            record.audit.append({"event": "denied", "at": now, "reason": record.decision_reason})
        elif policy == "disabled":
            record.status = "denied"
            record.decision_reason = "bluetooth_policy_disabled"
            record.audit.append({"event": "denied", "at": now, "reason": record.decision_reason})
        elif policy in {"allowed", "trusted_only"}:
            record, token = self._grant(record, duration_s=body.duration_s)
        self._store.upsert(record)
        return record, token

    def decide(self, request_id: str, body: HardwareAccessDecisionBody, *, actor_id: str) -> tuple[HardwareAccessRecord, str | None]:
        record = self._store.get(request_id)
        if record is None:
            raise KeyError("hardware_access_request_not_found")
        if record.status != "pending":
            raise ValueError("hardware_access_request_not_pending")
        now = utcnow_iso()
        record.decided_at = now
        record.decided_by = clean_text(actor_id, "admin")
        record.decision_reason = clean_text(body.reason) or None
        record.updated_at = now
        if body.decision == "deny":
            record.status = "denied"
            record.audit.append({"event": "denied", "at": now, "actor_id": record.decided_by, "reason": record.decision_reason})
            self._store.upsert(record)
            return record, None
        supervisor = self._resolve_supervisor(record.supervisor_id)
        if supervisor is None:
            record.status = "denied"
            record.decision_reason = "bluetooth_supervisor_unavailable"
            record.audit.append({"event": "denied", "at": now, "actor_id": record.decided_by, "reason": record.decision_reason})
            self._store.upsert(record)
            return record, None
        record, token = self._grant(record, duration_s=body.duration_s)
        record.audit.append({"event": "approved", "at": now, "actor_id": record.decided_by})
        self._store.upsert(record)
        return record, token

    def release(self, lease_id: str, *, node_id: str) -> HardwareAccessRecord:
        node_key = clean_text(node_id)
        lease_key = clean_text(lease_id)
        for record in self._store.list(node_id=node_key):
            if record.lease_id == lease_key and record.status == "granted":
                now = utcnow_iso()
                record.status = "released"
                record.released_at = now
                record.updated_at = now
                record.audit.append({"event": "released", "at": now, "node_id": node_key})
                self._store.upsert(record)
                return record
        raise KeyError("hardware_access_lease_not_found")

    def list_for_node(self, node_id: str) -> list[HardwareAccessRecord]:
        self._expire_old_leases()
        return self._store.list(node_id=clean_text(node_id))

    def list_requests(self, *, status: str | None = None) -> list[HardwareAccessRecord]:
        self._expire_old_leases()
        return self._store.list(status=status)

    def validate_lease(self, body: HardwareLeaseValidationBody) -> dict[str, Any]:
        secret = hardware_lease_secret()
        if not secret:
            return {"ok": False, "valid": False, "error": "hardware_lease_secret_unconfigured"}
        try:
            _header, payload = verify_hs256(body.lease_token, [{"kid": "hardware-v1", "secret": secret}])
            claims = validate_claims(
                payload,
                audience=HARDWARE_LEASE_AUDIENCE,
                required_scopes=[f"hardware.bluetooth.{body.operation}"],
            )
        except ServiceTokenError as exc:
            return {"ok": True, "valid": False, "error": str(exc)}
        lease_id = clean_text(payload.get("lease_id") or claims.jti)
        record = self._store.get_by_lease(lease_id)
        if record is None:
            return {"ok": True, "valid": False, "error": "hardware_access_lease_not_found"}
        self._expire_old_leases()
        if record.status != "granted":
            return {"ok": True, "valid": False, "error": f"hardware_access_lease_{record.status}"}
        if record.node_id != clean_text(body.node_id) or payload.get("node_id") != clean_text(body.node_id):
            return {"ok": True, "valid": False, "error": "hardware_access_node_mismatch"}
        if record.resource_type != body.resource_type or payload.get("resource_type") != body.resource_type:
            return {"ok": True, "valid": False, "error": "hardware_access_resource_mismatch"}
        if record.operation != body.operation or payload.get("operation") != body.operation:
            return {"ok": True, "valid": False, "error": "hardware_access_operation_mismatch"}
        if clean_text(body.supervisor_id) and record.supervisor_id != clean_text(body.supervisor_id):
            return {"ok": True, "valid": False, "error": "hardware_access_supervisor_mismatch"}
        requested_adapter = clean_text(getattr(body, "adapter", None))
        token_adapter = clean_text(payload.get("adapter"))
        if requested_adapter and token_adapter and requested_adapter != token_adapter:
            return {"ok": True, "valid": False, "error": "hardware_access_adapter_mismatch"}
        return {
            "ok": True,
            "valid": True,
            "lease": record.to_api_dict(),
            "claims": claims.to_dict(),
        }

    def _select_supervisor(self, body: HardwareAccessRequestBody) -> object | None:
        candidates = active_bluetooth_supervisors(self._supervisor_store)
        supervisor_id = clean_text(body.supervisor_id)
        if supervisor_id:
            return next((record for record in candidates if clean_text(getattr(record, "supervisor_id", "")) == supervisor_id), None)
        return candidates[0] if candidates else None

    def _resolve_supervisor(self, supervisor_id: str | None) -> object | None:
        if not supervisor_id:
            return None
        if self._supervisor_store is None or not hasattr(self._supervisor_store, "get"):
            return None
        record = self._supervisor_store.get(supervisor_id)
        if record is None or not supervisor_has_bluetooth(record) or freshness_state(record) != "online":
            return None
        return record

    def _grant(self, record: HardwareAccessRecord, *, duration_s: int | None) -> tuple[HardwareAccessRecord, str]:
        secret = hardware_lease_secret()
        if not secret:
            record.status = "denied"
            record.decision_reason = "hardware_lease_secret_unconfigured"
            record.updated_at = utcnow_iso()
            record.audit.append({"event": "denied", "at": record.updated_at, "reason": record.decision_reason})
            return record, ""
        now_ts = utc_ts()
        ttl = duration_s or hardware_lease_ttl_s()
        exp_ts = now_ts + ttl
        lease_id = f"hwlease_{secrets.token_urlsafe(12)}"
        claims = {
            "sub": record.node_id,
            "aud": HARDWARE_LEASE_AUDIENCE,
            "scp": [f"hardware.bluetooth.{record.operation}"],
            "iat": now_ts,
            "exp": exp_ts,
            "jti": lease_id,
            "lease_id": lease_id,
            "node_id": record.node_id,
            "resource_type": record.resource_type,
            "operation": record.operation,
            "supervisor_id": record.supervisor_id,
            "adapter": record.adapter,
        }
        token = sign_hs256({"alg": "HS256", "typ": "JWT", "kid": "hardware-v1"}, claims, secret=secret)
        expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat()
        record.status = "granted"
        record.lease_id = lease_id
        record.expires_at = expires_at
        record.updated_at = utcnow_iso()
        record.token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        record.audit.append({"event": "granted", "at": record.updated_at, "lease_id": lease_id, "expires_at": expires_at})
        return record, token

    def _expire_old_leases(self) -> None:
        now = datetime.now(timezone.utc)
        for record in self._store.list(status="granted"):
            if not record.expires_at:
                continue
            try:
                expires = datetime.fromisoformat(record.expires_at.replace("Z", "+00:00"))
            except Exception:
                continue
            if expires <= now:
                record.status = "expired"
                record.updated_at = utcnow_iso()
                record.audit.append({"event": "expired", "at": record.updated_at})
                self._store.upsert(record)
