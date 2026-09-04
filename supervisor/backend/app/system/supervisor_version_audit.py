from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.system.supervisor_local_source import SupervisorLocalSourceGate
from app.system.supervisors import (
    SupervisorFleetRecord,
    SupervisorFleetStore,
    _clean_text,
    _freshness_reason,
    _freshness_state,
    _is_local_supervisor_record,
    _sanitize_update_payload,
    _supervisor_history_timeout_s,
)

log = logging.getLogger("hexe.supervisor.version_audit")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_interval_s(name: str, default: float) -> float:
    raw = str(os.getenv(name, str(default))).strip()
    try:
        return max(60.0, float(raw))
    except Exception:
        return default


@dataclass(frozen=True)
class SupervisorVersionAuditConfig:
    enabled: bool = True
    interval_s: float = 600.0

    @classmethod
    def from_env(cls) -> "SupervisorVersionAuditConfig":
        return cls(
            enabled=_env_bool("HEXE_SUPERVISOR_VERSION_AUDIT_ENABLED", True),
            interval_s=_env_interval_s("HEXE_SUPERVISOR_VERSION_AUDIT_INTERVAL_S", 600.0),
        )


@dataclass(frozen=True)
class SupervisorVersionReference:
    reported_version: str | None = None
    source_commit: str | None = None
    local_source_gate: dict[str, Any] | None = None


class SupervisorVersionAudit:
    def __init__(
        self,
        registry: SupervisorFleetStore,
        *,
        local_client: object | None = None,
        audit_store: object | None = None,
        local_source_gate: SupervisorLocalSourceGate | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.registry = registry
        self.local_client = local_client
        self.audit_store = audit_store
        self.local_source_gate = local_source_gate or SupervisorLocalSourceGate()
        self.timeout_s = timeout_s or _supervisor_history_timeout_s()

    def run_once(self) -> dict[str, Any]:
        started_at = _utcnow_iso()
        local_source_gate = self.local_source_gate.inspect()
        self._record_event(
            "supervisor_version_audit_started",
            details={"started_at": started_at, "local_source_gate": local_source_gate},
        )
        if _clean_text(local_source_gate.get("classification")) != "current":
            self._record_event(
                "supervisor_local_source_gate_blocked",
                status=_clean_text(local_source_gate.get("classification"), "unknown"),
                details={
                    "reason": local_source_gate.get("reason"),
                    "auto_update_blocker": local_source_gate.get("auto_update_blocker"),
                },
            )
        records = self.registry.list(include_historical=False)
        local_results = self._inspect_local_records(
            [record for record in records if _is_local_supervisor_record(record)],
            local_source_gate=local_source_gate,
        )
        reference = self._reference_from_results(local_results, local_source_gate=local_source_gate)
        remote_results = [
            self._inspect_remote_record(record, reference)
            for record in self.registry.list(include_historical=False)
            if not _is_local_supervisor_record(record)
        ]
        results = local_results + remote_results
        counts: dict[str, int] = {}
        for result in results:
            classification = _clean_text(result.get("classification"), "unknown")
            counts[classification] = counts.get(classification, 0) + 1
        completed = {
            "ok": True,
            "started_at": started_at,
            "completed_at": _utcnow_iso(),
            "count": len(results),
            "counts": counts,
            "local_source_gate": local_source_gate,
        }
        self._record_event("supervisor_version_audit_completed", details=completed)
        return completed

    def _inspect_local_records(
        self,
        records: list[SupervisorFleetRecord],
        *,
        local_source_gate: dict[str, Any],
    ) -> list[dict[str, Any]]:
        request_json = getattr(self.local_client, "request_json", None)
        if not callable(request_json):
            return [
                self._store_audit_result(
                    record,
                    self._apply_local_source_gate(
                        self._failure(record, "unreachable", "supervisor_client_unavailable"),
                        local_source_gate,
                    ),
                    local_source_gate=local_source_gate,
                )
                for record in records
            ]
        if not records:
            status = self._request_local_status(request_json)
            if not isinstance(status, dict):
                return []
            supervisor_id = _clean_text(status.get("supervisor_id"), "local-core-supervisor")
            self.registry.register(
                self._registration_request(
                    supervisor_id=supervisor_id,
                    supervisor_version=_clean_text(status.get("reported_version")) or None,
                    transport="local",
                    metadata={"attached_to_core": True, "reporter": "supervisor-version-audit"},
                )
            )
            records = [record for record in self.registry.list(include_historical=False) if record.supervisor_id == supervisor_id]
        results: list[dict[str, Any]] = []
        for record in records:
            status = self._request_local_status(request_json)
            result = self._apply_local_source_gate(
                self._status_result(record, status, reference=None, source="local"),
                local_source_gate,
            )
            results.append(
                self._store_audit_result(
                    record,
                    result,
                    update_status=status if isinstance(status, dict) else None,
                    local_source_gate=local_source_gate,
                )
            )
        return results

    def _inspect_remote_record(self, record: SupervisorFleetRecord, reference: SupervisorVersionReference) -> dict[str, Any]:
        if _clean_text(record.trust_status, "trusted") != "trusted":
            return self._store_audit_result(record, self._failure(record, "unsupported", "supervisor_not_trusted"))
        freshness = _freshness_state(record.last_seen_at)
        if freshness != "online":
            return self._store_audit_result(
                record,
                self._failure(record, "unreachable", _freshness_reason(record), freshness_state=freshness),
            )
        base_url = _clean_text(record.api_base_url).rstrip("/")
        if not base_url:
            result = self._failure(record, "unreachable", "supervisor_api_base_url_missing")
            self._record_api_failure(record, result)
            return self._store_audit_result(record, result)
        try:
            response = httpx.request("GET", f"{base_url}/api/supervisor/update/status", timeout=self.timeout_s)
        except httpx.HTTPError:
            result = self._failure(record, "unreachable", "supervisor_update_api_unavailable")
            self._record_api_failure(record, result)
            return self._store_audit_result(record, result)
        if response.status_code == 404:
            result = self._failure(record, "unsupported", "supervisor_update_api_not_found")
            self._record_api_failure(record, result)
            return self._store_audit_result(record, result)
        if response.status_code >= 400:
            result = self._failure(record, "unreachable", "supervisor_update_api_error", status_code=response.status_code)
            self._record_api_failure(record, result)
            return self._store_audit_result(record, result)
        try:
            status = response.json()
        except ValueError:
            result = self._failure(record, "unknown", "supervisor_update_api_invalid_json")
            self._record_api_failure(record, result)
            return self._store_audit_result(record, result)
        result = self._status_result(record, status, reference=reference, source="remote")
        result = self._apply_local_source_gate(result, reference.local_source_gate)
        if result.get("classification") in {"unknown", "unsupported"}:
            self._record_api_failure(record, result)
        return self._store_audit_result(
            record,
            result,
            update_status=status if isinstance(status, dict) else None,
            local_source_gate=reference.local_source_gate,
        )

    def _request_local_status(self, request_json: object) -> dict[str, Any] | None:
        try:
            status = request_json("GET", "/api/supervisor/update/status")
        except Exception:
            return None
        return status if isinstance(status, dict) else None

    def _status_result(
        self,
        record: SupervisorFleetRecord,
        status: object,
        *,
        reference: SupervisorVersionReference | None,
        source: str,
    ) -> dict[str, Any]:
        if not isinstance(status, dict):
            return self._failure(record, "unknown", "supervisor_update_api_invalid_payload", source=source)
        supported_modes = status.get("supported_modes")
        if supported_modes is not None and not isinstance(supported_modes, list):
            return self._failure(record, "unknown", "supervisor_update_status_invalid_payload", source=source)
        update_state = _clean_text(status.get("update_state"), "idle").lower()
        if update_state in {"starting", "running"}:
            classification = "update_running"
            reason = "update_running"
        elif not supported_modes:
            classification = "unsupported"
            reason = "supervisor_update_modes_missing"
        else:
            classification, reason = self._classify_currentness(status, reference)
        return {
            "schema_version": "1",
            "supervisor_id": record.supervisor_id,
            "classification": classification,
            "reason": reason,
            "source": source,
            "freshness_state": _freshness_state(record.last_seen_at),
            "api_reachable": True,
            "reported_version": _clean_text(status.get("reported_version")) or record.supervisor_version,
            "source_commit": self._status_commit(status),
            "supported_modes": [str(item) for item in supported_modes or []],
            "update_state": update_state,
            "reference": {
                "reported_version": reference.reported_version if reference else _clean_text(status.get("reported_version")) or None,
                "source_commit": reference.source_commit if reference else self._status_commit(status),
            },
            "checked_at": _utcnow_iso(),
        }

    def _apply_local_source_gate(self, result: dict[str, Any], local_source_gate: dict[str, Any] | None) -> dict[str, Any]:
        if not local_source_gate:
            return result
        gated = {**result, "local_source_gate": local_source_gate}
        if _clean_text(local_source_gate.get("classification")) == "current":
            gated["local_source_gate_allows_remote_update"] = True
            return gated
        gated["local_source_gate_allows_remote_update"] = False
        gated["auto_update_blocker"] = local_source_gate.get("auto_update_blocker") or local_source_gate.get("reason")
        if _clean_text(gated.get("classification")) != "update_running":
            gated["classification"] = "unknown"
            gated["reason"] = "local_source_not_current"
        return gated

    def _classify_currentness(
        self,
        status: dict[str, Any],
        reference: SupervisorVersionReference | None,
    ) -> tuple[str, str]:
        git = status.get("git") if isinstance(status.get("git"), dict) else {}
        if bool(git.get("update_available")):
            return "outdated", "git_update_available"
        try:
            behind = int(git.get("behind")) if git.get("behind") is not None else 0
        except Exception:
            behind = 0
        if behind > 0:
            return "outdated", "git_behind_upstream"
        reported_version = _clean_text(status.get("reported_version"))
        source_commit = self._status_commit(status)
        if reference and reference.source_commit and source_commit:
            return ("current", "source_commit_matches_local") if source_commit == reference.source_commit else (
                "outdated",
                "source_commit_differs_from_local",
            )
        if reference and reference.reported_version and reported_version:
            return ("current", "reported_version_matches_local") if reported_version == reference.reported_version else (
                "outdated",
                "reported_version_differs_from_local",
            )
        if reference is None and (reported_version or source_commit):
            return "current", "local_supervisor_reference"
        if reported_version or source_commit:
            return "unknown", "local_reference_missing"
        return "unknown", "reported_version_missing"

    def _store_audit_result(
        self,
        record: SupervisorFleetRecord,
        result: dict[str, Any],
        *,
        update_status: dict[str, Any] | None = None,
        local_source_gate: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous = {}
        current = self.registry.get(record.supervisor_id)
        if current is not None and isinstance(current.metadata, dict):
            previous = dict(current.metadata.get("version_audit") or {}) if isinstance(current.metadata.get("version_audit"), dict) else {}
        stored = self.registry.set_version_audit_status(
            record.supervisor_id,
            result,
            update_status=update_status,
            local_source_gate=local_source_gate,
            supervisor_version=_clean_text(result.get("reported_version")) or None,
        )
        changed = _clean_text(previous.get("classification")) != _clean_text(result.get("classification"))
        if changed:
            self._record_event(
                "supervisor_version_classification_changed",
                supervisor_id=record.supervisor_id,
                status=_clean_text(result.get("classification"), "unknown"),
                details={
                    "previous": _clean_text(previous.get("classification")) or None,
                    "current": _clean_text(result.get("classification"), "unknown"),
                    "reason": result.get("reason"),
                    "freshness_state": result.get("freshness_state"),
                },
            )
        return dict(stored.metadata.get("version_audit") or result)

    def _failure(
        self,
        record: SupervisorFleetRecord,
        classification: str,
        reason: str,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "supervisor_id": record.supervisor_id,
            "classification": classification,
            "reason": reason,
            "source": "remote" if not _is_local_supervisor_record(record) else "local",
            "freshness_state": extra.pop("freshness_state", _freshness_state(record.last_seen_at)),
            "api_reachable": False,
            "reported_version": record.supervisor_version,
            "source_commit": None,
            "supported_modes": [],
            "update_state": None,
            "checked_at": _utcnow_iso(),
            **extra,
        }

    def _reference_from_results(
        self,
        results: list[dict[str, Any]],
        *,
        local_source_gate: dict[str, Any],
    ) -> SupervisorVersionReference:
        for result in results:
            if _clean_text(result.get("classification")) in {"current", "update_running", "unknown", "unsupported"}:
                return SupervisorVersionReference(
                    reported_version=_clean_text(result.get("reported_version")) or _clean_text(os.getenv("HEXE_CORE_VERSION")) or None,
                    source_commit=_clean_text(result.get("source_commit")) or None,
                    local_source_gate=local_source_gate,
                )
        return SupervisorVersionReference(
            reported_version=_clean_text(os.getenv("HEXE_CORE_VERSION")) or None,
            local_source_gate=local_source_gate,
        )

    @staticmethod
    def _status_commit(status: dict[str, Any]) -> str | None:
        git = status.get("git") if isinstance(status.get("git"), dict) else {}
        return _clean_text(git.get("local_sha")) or _clean_text(status.get("source_commit")) or None

    @staticmethod
    def _registration_request(**kwargs: Any) -> Any:
        from app.system.supervisors import SupervisorRegistrationRequest

        return SupervisorRegistrationRequest(**kwargs)

    def _record_api_failure(self, record: SupervisorFleetRecord, result: dict[str, Any]) -> None:
        self._record_event(
            "supervisor_version_audit_api_failed",
            supervisor_id=record.supervisor_id,
            status=_clean_text(result.get("classification"), "unknown"),
            details={"reason": result.get("reason"), "freshness_state": result.get("freshness_state")},
        )

    def _record_event(
        self,
        event_type: str,
        *,
        supervisor_id: str | None = None,
        status: str = "success",
        details: dict[str, Any],
    ) -> None:
        record_sync = getattr(self.audit_store, "record_sync", None)
        if not callable(record_sync):
            return
        payload = {"status": status, **details}
        if supervisor_id:
            payload["supervisor_id"] = supervisor_id
        record_sync(
            event_type=event_type,
            actor_role="system",
            actor_id="supervisor-version-audit",
            details=_sanitize_update_payload(payload),
        )


async def supervisor_version_audit_loop(app: Any, config: SupervisorVersionAuditConfig | None = None) -> None:
    cfg = config or SupervisorVersionAuditConfig.from_env()
    if not cfg.enabled:
        return
    while True:
        try:
            registry = getattr(app.state, "supervisor_fleet_store", None)
            if registry is not None:
                SupervisorVersionAudit(
                    registry,
                    local_client=getattr(app.state, "supervisor_client", None),
                    audit_store=getattr(app.state, "audit_store", None),
                    local_source_gate=getattr(app.state, "supervisor_local_source_gate", None),
                ).run_once()
        except Exception:
            log.exception("Supervisor version audit loop failed")
        await asyncio.sleep(cfg.interval_s)
