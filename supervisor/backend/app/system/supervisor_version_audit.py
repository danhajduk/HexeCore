from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.supervisor.config import supervisor_reported_version
from app.supervisor.update_package import SupervisorUpdatePackageError, build_supervisor_update_package
from app.system.supervisor_local_source import SupervisorLocalSourceGate
from app.system.supervisors import (
    SupervisorFleetRecord,
    SupervisorFleetStore,
    _clean_text,
    _freshness_reason,
    _freshness_state,
    _is_local_supervisor_record,
    _sanitize_update_payload,
    _source_commit_sha,
    _supervisor_package_source_root,
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


def _env_positive_int(name: str, default: int, *, upper: int | None = None) -> int:
    raw = str(os.getenv(name, str(default))).strip()
    try:
        value = max(1, int(raw))
    except Exception:
        value = default
    return min(value, upper) if upper is not None else value


def _env_id_set(name: str) -> frozenset[str]:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return frozenset()
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def _parse_iso(value: object) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


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


@dataclass(frozen=True)
class SupervisorAutoUpdateConfig:
    enabled: bool = False
    source_mode: str = "core_host"
    max_parallel: int = 1
    allowed_ids: frozenset[str] = frozenset()
    denied_ids: frozenset[str] = frozenset()
    require_healthy: bool = True
    failure_backoff_s: int = 30 * 60

    @classmethod
    def from_env(cls) -> "SupervisorAutoUpdateConfig":
        source_mode = _clean_text(os.getenv("HEXE_SUPERVISOR_AUTO_UPDATE_SOURCE_MODE"), "core_host").lower()
        if source_mode not in {"git", "core_host"}:
            source_mode = "core_host"
        return cls(
            enabled=_env_bool("HEXE_SUPERVISOR_AUTO_UPDATE_ENABLED", False),
            source_mode=source_mode,
            max_parallel=_env_positive_int("HEXE_SUPERVISOR_AUTO_UPDATE_MAX_PARALLEL", 1, upper=20),
            allowed_ids=_env_id_set("HEXE_SUPERVISOR_AUTO_UPDATE_ALLOWED_IDS"),
            denied_ids=_env_id_set("HEXE_SUPERVISOR_AUTO_UPDATE_DENIED_IDS"),
            require_healthy=_env_bool("HEXE_SUPERVISOR_AUTO_UPDATE_REQUIRE_HEALTHY", True),
        )


class SupervisorAutoUpdateTrigger:
    def __init__(
        self,
        registry: SupervisorFleetStore,
        *,
        audit_store: object | None = None,
        ble_pairing_sessions: object | None = None,
        config: SupervisorAutoUpdateConfig | None = None,
        timeout_s: float | None = None,
        http_request: object | None = None,
        package_builder: object | None = None,
    ) -> None:
        self.registry = registry
        self.audit_store = audit_store
        self.ble_pairing_sessions = ble_pairing_sessions
        self.config = config or SupervisorAutoUpdateConfig.from_env()
        self.timeout_s = timeout_s or _supervisor_history_timeout_s()
        self.http_request = http_request or httpx.request
        self.package_builder = package_builder or build_supervisor_update_package

    def run(self, reference: SupervisorVersionReference, *, local_source_gate: dict[str, Any]) -> dict[str, Any]:
        started = 0
        decisions: list[dict[str, Any]] = []
        for record in self.registry.list(include_historical=False):
            if _is_local_supervisor_record(record):
                continue
            can_start_more = started < self.config.max_parallel
            decision = self._decision_for_record(record, reference, local_source_gate, can_start_more=can_start_more)
            if decision.get("action") == "start":
                started += 1
            decisions.append(decision)
            self.registry.set_auto_update_decision(record.supervisor_id, decision)
            self._record_event(record.supervisor_id, decision)
        counts: dict[str, int] = {}
        for decision in decisions:
            status = _clean_text(decision.get("decision"), "unknown")
            counts[status] = counts.get(status, 0) + 1
        return {
            "enabled": self.config.enabled,
            "source_mode": self.config.source_mode,
            "max_parallel": self.config.max_parallel,
            "started": started,
            "count": len(decisions),
            "counts": counts,
        }

    def _decision_for_record(
        self,
        record: SupervisorFleetRecord,
        reference: SupervisorVersionReference,
        local_source_gate: dict[str, Any],
        *,
        can_start_more: bool,
    ) -> dict[str, Any]:
        checked_at = _utcnow_iso()
        base = {
            "schema_version": "1",
            "supervisor_id": record.supervisor_id,
            "source_mode": self.config.source_mode,
            "target_version": reference.reported_version,
            "target_source_commit": self._target_source_commit(reference, local_source_gate),
            "checked_at": checked_at,
            "auto_update_enabled": self.config.enabled,
        }
        blocker = self._preflight_blocker(record, local_source_gate)
        if blocker:
            return {**base, "decision": "blocked", "reason": blocker}

        version_audit = dict(record.metadata.get("version_audit") or {}) if isinstance(record.metadata, dict) else {}
        if _clean_text(version_audit.get("classification")) != "outdated":
            return {**base, "decision": "skipped", "reason": f"supervisor_not_outdated:{_clean_text(version_audit.get('classification'), 'unknown')}"}

        supported_modes = version_audit.get("supported_modes") if isinstance(version_audit.get("supported_modes"), list) else []
        if self.config.source_mode not in {str(item) for item in supported_modes}:
            return {**base, "decision": "blocked", "reason": "supervisor_update_mode_unsupported"}

        if _clean_text(version_audit.get("update_state"), "idle").lower() in {"starting", "running"}:
            return {**base, "decision": "blocked", "reason": "update_running"}

        if not self.config.enabled:
            return {**base, "decision": "recommended", "reason": "auto_update_disabled"}

        prior = dict(record.metadata.get("auto_update_decision") or {}) if isinstance(record.metadata, dict) else {}
        idempotency_key = self._idempotency_key(record, base)
        if self._same_target(prior, base) and _clean_text(prior.get("idempotency_key")) == idempotency_key:
            if _clean_text(prior.get("decision")) in {"started", "replayed"}:
                return {**base, "decision": "skipped", "reason": "already_triggered_for_target", "idempotency_key": idempotency_key}
            if self._failure_backoff_active(prior):
                return {**base, "decision": "blocked", "reason": "failure_backoff_active", "idempotency_key": idempotency_key}

        if not can_start_more:
            return {**base, "decision": "blocked", "reason": "max_parallel_limit"}

        try:
            status = self._request_update_status(record)
        except SupervisorAutoUpdateError as exc:
            return {**base, "decision": "failed", "reason": exc.reason, "idempotency_key": idempotency_key, "last_failure_at": checked_at}
        refreshed_modes = status.get("supported_modes") if isinstance(status.get("supported_modes"), list) else []
        if self.config.source_mode not in {str(item) for item in refreshed_modes}:
            return {**base, "decision": "blocked", "reason": "supervisor_update_mode_unsupported", "idempotency_key": idempotency_key}
        if _clean_text(status.get("update_state"), "idle").lower() in {"starting", "running"}:
            self.registry.set_update_status(record.supervisor_id, status)
            return {**base, "decision": "blocked", "reason": "update_running", "idempotency_key": idempotency_key}

        try:
            payload = self._start_payload(record, idempotency_key)
            result = self._request_update_start(record, payload)
        except SupervisorAutoUpdateError as exc:
            return {**base, "decision": "failed", "reason": exc.reason, "idempotency_key": idempotency_key, "last_failure_at": checked_at}
        post_status = dict(result.get("status") or {}) if isinstance(result.get("status"), dict) else {}
        post_refresh_error = None
        try:
            post_status = self._request_update_status(record)
        except SupervisorAutoUpdateError as exc:
            post_refresh_error = exc.reason
        if post_status:
            self.registry.set_update_status(record.supervisor_id, post_status)

        accepted = bool(result.get("accepted"))
        request_id = self._update_request_id(result, post_status)
        decision = {
            **base,
            "decision": "started" if accepted else "replayed",
            "reason": "remote_update_started" if accepted else "remote_update_replayed",
            "action": "start",
            "idempotency_key": idempotency_key,
            "update_request_id": request_id,
            "package_id": payload.get("package_id") if self.config.source_mode == "core_host" else None,
            "last_triggered_at": checked_at,
        }
        if post_refresh_error:
            decision["post_update_status_refresh"] = "failed"
            decision["post_update_status_refresh_reason"] = post_refresh_error
        else:
            decision["post_update_status_refresh"] = "success"
        return decision

    def _preflight_blocker(self, record: SupervisorFleetRecord, local_source_gate: dict[str, Any]) -> str | None:
        if _clean_text(local_source_gate.get("classification")) != "current":
            return "local_source_not_current"
        if _clean_text(record.trust_status, "trusted") != "trusted":
            return "supervisor_not_trusted"
        freshness = _freshness_state(record.last_seen_at)
        if freshness != "online":
            return f"supervisor_not_online:{freshness}"
        if not _clean_text(record.api_base_url):
            return "supervisor_api_base_url_missing"
        if record.supervisor_id in self.config.denied_ids:
            return "supervisor_auto_update_denied"
        if self.config.allowed_ids and record.supervisor_id not in self.config.allowed_ids:
            return "supervisor_auto_update_not_allowed"
        if self.config.require_healthy and _clean_text(record.health_status, "unknown").lower() not in {"healthy", "ok"}:
            return "supervisor_health_not_healthy"
        if self._has_active_ble_pairing_session(record.supervisor_id):
            return "ble_pairing_session_active"
        return None

    def _request_update_status(self, record: SupervisorFleetRecord) -> dict[str, Any]:
        result = self._request_remote(record, "GET", "/api/supervisor/update/status")
        if not isinstance(result.get("supported_modes", []), list):
            raise SupervisorAutoUpdateError("supervisor_update_status_invalid_payload")
        return result

    def _request_update_start(self, record: SupervisorFleetRecord, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_remote(record, "POST", "/api/supervisor/update/start", payload=payload)

    def _request_remote(
        self,
        record: SupervisorFleetRecord,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base_url = _clean_text(record.api_base_url).rstrip("/")
        if not base_url:
            raise SupervisorAutoUpdateError("supervisor_api_base_url_missing")
        try:
            response = self.http_request(method.upper(), f"{base_url}{path}", json=payload, timeout=self.timeout_s)
        except httpx.HTTPError as exc:
            raise SupervisorAutoUpdateError("supervisor_update_api_unavailable") from exc
        if response.status_code == 404:
            raise SupervisorAutoUpdateError("supervisor_update_api_not_found")
        if response.status_code >= 400:
            raise SupervisorAutoUpdateError("supervisor_update_api_error")
        try:
            result = response.json()
        except ValueError as exc:
            raise SupervisorAutoUpdateError("supervisor_update_api_invalid_json") from exc
        if not isinstance(result, dict):
            raise SupervisorAutoUpdateError("supervisor_update_api_invalid_payload")
        return result

    def _start_payload(self, record: SupervisorFleetRecord, idempotency_key: str) -> dict[str, Any]:
        payload = {
            "source_mode": self.config.source_mode,
            "idempotency_key": idempotency_key,
            "service_update": True,
        }
        if self.config.source_mode != "core_host":
            return payload
        source_root = _supervisor_package_source_root()
        try:
            package = self.package_builder(
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
            raise SupervisorAutoUpdateError(f"supervisor_update_package_build_failed:{exc}") from exc
        except Exception as exc:
            raise SupervisorAutoUpdateError("supervisor_update_package_build_failed") from exc
        return {**payload, **package.to_request_payload()}

    def _idempotency_key(self, record: SupervisorFleetRecord, base: dict[str, Any]) -> str:
        raw = "|".join(
            [
                record.supervisor_id,
                self.config.source_mode,
                _clean_text(base.get("target_version")),
                _clean_text(base.get("target_source_commit")),
            ]
        )
        return f"supervisor-auto-update-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"

    @staticmethod
    def _target_source_commit(reference: SupervisorVersionReference, local_source_gate: dict[str, Any]) -> str | None:
        return _clean_text(local_source_gate.get("head")) or reference.source_commit

    @staticmethod
    def _same_target(prior: dict[str, Any], base: dict[str, Any]) -> bool:
        return (
            _clean_text(prior.get("source_mode")) == _clean_text(base.get("source_mode"))
            and _clean_text(prior.get("target_version")) == _clean_text(base.get("target_version"))
            and _clean_text(prior.get("target_source_commit")) == _clean_text(base.get("target_source_commit"))
        )

    def _failure_backoff_active(self, prior: dict[str, Any]) -> bool:
        last_failure = _parse_iso(prior.get("last_failure_at"))
        if last_failure is None:
            return False
        return (datetime.now(timezone.utc) - last_failure).total_seconds() < self.config.failure_backoff_s

    def _has_active_ble_pairing_session(self, supervisor_id: str) -> bool:
        sessions = self._list_ble_pairing_sessions()
        for session in sessions:
            status = _clean_text(self._session_value(session, "status")).lower()
            if status not in {"waiting", "found", "approved"}:
                continue
            session_supervisor_id = _clean_text(self._session_value(session, "supervisor_id"))
            if session_supervisor_id and session_supervisor_id == supervisor_id:
                return True
            results = self._session_value(session, "supervisor_results")
            if not isinstance(results, list):
                continue
            for item in results:
                if not isinstance(item, dict):
                    continue
                if _clean_text(item.get("supervisor_id")) != supervisor_id:
                    continue
                if _clean_text(item.get("status"), "pending").lower() in {"pending", "advertising", "endpoint_identity_received"}:
                    return True
        return False

    def _list_ble_pairing_sessions(self) -> list[Any]:
        if self.ble_pairing_sessions is None:
            return []
        list_sessions = getattr(self.ble_pairing_sessions, "list_sessions", None)
        if callable(list_sessions):
            try:
                return list(list_sessions())
            except Exception:
                return []
        list_records = getattr(self.ble_pairing_sessions, "list", None)
        if callable(list_records):
            try:
                return list(list_records())
            except Exception:
                return []
        return []

    @staticmethod
    def _session_value(session: object, key: str) -> Any:
        if isinstance(session, dict):
            return session.get(key)
        return getattr(session, key, None)

    @staticmethod
    def _update_request_id(result: dict[str, Any], post_status: dict[str, Any]) -> str | None:
        for source in (result, dict(result.get("status") or {}), post_status, dict(post_status.get("current_update") or {})):
            request_id = _clean_text(source.get("request_id") if isinstance(source, dict) else None)
            if request_id:
                return request_id
        return None

    def _record_event(self, supervisor_id: str, decision: dict[str, Any]) -> None:
        record_sync = getattr(self.audit_store, "record_sync", None)
        if not callable(record_sync):
            return
        record_sync(
            event_type="supervisor_auto_update_decision",
            actor_role="system",
            actor_id="supervisor-version-audit",
            details=_sanitize_update_payload({"supervisor_id": supervisor_id, **decision}),
        )


class SupervisorAutoUpdateError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SupervisorVersionAudit:
    def __init__(
        self,
        registry: SupervisorFleetStore,
        *,
        local_client: object | None = None,
        audit_store: object | None = None,
        local_source_gate: SupervisorLocalSourceGate | None = None,
        auto_update_trigger: SupervisorAutoUpdateTrigger | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.registry = registry
        self.local_client = local_client
        self.audit_store = audit_store
        self.local_source_gate = local_source_gate or SupervisorLocalSourceGate()
        self.auto_update_trigger = auto_update_trigger
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
        trigger = self.auto_update_trigger or SupervisorAutoUpdateTrigger(
            self.registry,
            audit_store=self.audit_store,
            timeout_s=self.timeout_s,
        )
        completed["auto_update"] = trigger.run(reference, local_source_gate=local_source_gate)
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
                    auto_update_trigger=SupervisorAutoUpdateTrigger(
                        registry,
                        audit_store=getattr(app.state, "audit_store", None),
                        ble_pairing_sessions=getattr(app.state, "hardware_ble_pairing_session_service", None)
                        or getattr(app.state, "hardware_ble_pairing_session_store", None),
                    ),
                ).run_once()
        except Exception:
            log.exception("Supervisor version audit loop failed")
        await asyncio.sleep(cfg.interval_s)
