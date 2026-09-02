from __future__ import annotations

import os
import socket
import base64
import hashlib
import json
import shlex
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Any
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException

from app.system.onboarding import NodeRegistrationsStore
from app.core.env import getenv
from app.system.auth.tokens import ServiceTokenError, validate_claims, verify_hs256
from app.system.hardware import (
    BLE_PROVISIONING_CONTRACT_VERSION,
    BLE_PROVISIONING_ENCRYPTION_ALGORITHM,
    BLE_PROVISIONING_ENVELOPE_SCHEMA_VERSION,
    BLE_PROVISIONING_KEY_AGREEMENT,
    HARDWARE_LEASE_AUDIENCE,
    hardware_lease_secret,
)
from app.system.runtime import StandaloneRuntimeService
from app.system.stats.models import SystemStats, SystemStatsSnapshot
from app.system.stats.service import collect_process_stats, collect_system_snapshot, collect_system_stats
from hexe_supervisor.docker_compose import compose_down, compose_up

from .models import (
    HostIdentitySummary,
    HostResourceSummary,
    ManagedNodeSummary,
    ProcessResourceSummary,
    SupervisorAdmissionContextSummary,
    SupervisorBluetoothBleScanRequest,
    SupervisorBluetoothLeaseRequest,
    SupervisorBluetoothProvisionWifiRequest,
    SupervisorCoreRuntimeActionResult,
    SupervisorCoreRuntimeHeartbeatRequest,
    SupervisorCoreRuntimeRegistrationRequest,
    SupervisorCoreRuntimeSummary,
    SupervisorHealthSummary,
    SupervisorInfoSummary,
    SupervisorNodeActionResult,
    SupervisorNodeServiceActionResult,
    SupervisorNodeServiceSummary,
    SupervisorNodeServicesSummary,
    SupervisorOwnershipBoundary,
    SupervisorRegisteredRuntimeSummary,
    SupervisorRuntimeActionResult,
    SupervisorRuntimeHeartbeatRequest,
    SupervisorRuntimeRegistrationRequest,
    SupervisorRuntimeSummary,
    SupervisorUpdateStartRequest,
    SupervisorUpdateStartResult,
    SupervisorUpdateStatusSummary,
)
from .boot_order import load_boot_order_plan
from .core_runtime_store import SupervisorCoreRuntimeRecord, SupervisorCoreRuntimeStore
from .resource_history_store import SupervisorResourceHistoryStore
from .resource_monitor import SupervisorResourceMonitor
from .runtime_nodes import merge_runtime_identity
from .runtime_store import SupervisorRuntimeNodeRecord, SupervisorRuntimeNodesStore


class DisabledBleProvisioningBackend:
    def provision_wifi(
        self,
        *,
        adapter: dict[str, Any],
        validation: dict[str, Any],
        envelope: dict[str, Any],
        target_address: str | None,
        timeout_s: int,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "failed",
            "ack": False,
            "error": "gatt_backend_unavailable",
            "message": "No Supervisor BLE provisioning backend is configured.",
        }


class SupervisorDomainService:
    def __init__(
        self,
        runtime_service: StandaloneRuntimeService | None = None,
        runtime_nodes_store: SupervisorRuntimeNodesStore | None = None,
        core_runtime_store: SupervisorCoreRuntimeStore | None = None,
        node_registrations_store: NodeRegistrationsStore | None = None,
        resource_monitor: SupervisorResourceMonitor | None = None,
        resource_history_store: SupervisorResourceHistoryStore | None = None,
        ble_provisioning_backend: object | None = None,
        install_root: Path | None = None,
    ) -> None:
        self._runtime_service = runtime_service or StandaloneRuntimeService()
        self._runtime_nodes_store = runtime_nodes_store or SupervisorRuntimeNodesStore()
        self._core_runtime_store = core_runtime_store or SupervisorCoreRuntimeStore()
        self._node_registrations_store = node_registrations_store
        self._resource_monitor = resource_monitor or SupervisorResourceMonitor()
        self._resource_history_store = resource_history_store or SupervisorResourceHistoryStore()
        self._ble_provisioning_backend = ble_provisioning_backend or DisabledBleProvisioningBackend()
        self._install_root_override = install_root
        self._ble_provisioning_events: list[dict[str, Any]] = []
        self._boot_loop_status: dict[str, Any] = {
            "state": "idle",
            "updated_at": self._now_iso(),
        }
        self._bluetooth_power_last_attempt_s = 0.0
        self._bluetooth_power_error: str | None = None

    def _install_root(self) -> Path:
        return self._install_root_override or Path(__file__).resolve().parents[3]

    def _update_state_path(self) -> Path:
        return self._install_root() / "var" / "supervisor" / "update-state.json"

    def _runtime_provider(self) -> str:
        return str(getenv("HEXE_MQTT_RUNTIME_PROVIDER", "docker")).strip().lower() or "docker"

    def _host_identity(self) -> HostIdentitySummary:
        hostname = socket.gethostname()
        return HostIdentitySummary(
            host_id=hostname,
            hostname=hostname,
            runtime_provider=self._runtime_provider(),
        )

    def _supervisor_id(self) -> str:
        configured = str(getenv("HEXE_SUPERVISOR_ID") or "").strip()
        return configured or f"{self._host_identity().hostname}-supervisor"

    def _env_bool(self, name: str, default: bool) -> bool:
        raw = str(getenv(name, "")).strip().lower()
        if not raw:
            return default
        return raw in {"1", "true", "yes", "on"}

    def _supervisor_version(self) -> str | None:
        value = str(getenv("HEXE_CORE_VERSION") or "").strip()
        return value or None

    def _read_update_state(self) -> dict[str, Any]:
        path = self._update_state_path()
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return dict(payload) if isinstance(payload, dict) else {}

    def _write_update_state(self, payload: dict[str, Any]) -> None:
        path = self._update_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _redact_update_text(self, value: object) -> str:
        text = str(value or "")
        if not text:
            return ""
        redacted: list[str] = []
        for line in text.splitlines():
            lowered = line.lower()
            if any(marker in lowered for marker in ("token", "password", "secret", "credential", "private_key", "authorization")):
                redacted.append("[REDACTED]")
            else:
                redacted.append(line[:500])
        return "\n".join(redacted)[-4000:]

    def _run_git(self, args: list[str], *, timeout_s: float = 5.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self._install_root(),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )

    def _run_systemctl_user(self, args: list[str], *, timeout_s: float = 8.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["systemctl", "--user", *args],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )

    def _git_update_status(self) -> dict[str, Any]:
        install_root = self._install_root()
        status: dict[str, Any] = {
            "path": str(install_root),
            "is_git_checkout": False,
        }
        if not (install_root / ".git").exists():
            status["error"] = "not_git_checkout"
            return status
        inside = self._run_git(["rev-parse", "--is-inside-work-tree"])
        if inside.returncode != 0 or (inside.stdout or "").strip() != "true":
            status["error"] = self._redact_update_text(inside.stderr or inside.stdout) or "not_git_checkout"
            return status
        status["is_git_checkout"] = True

        def git_text(args: list[str]) -> str | None:
            result = self._run_git(args)
            return (result.stdout or "").strip() if result.returncode == 0 else None

        branch = git_text(["rev-parse", "--abbrev-ref", "HEAD"])
        local_sha = git_text(["rev-parse", "HEAD"])
        upstream = git_text(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
        remote_sha = git_text(["rev-parse", upstream]) if upstream else None
        counts = git_text(["rev-list", "--left-right", "--count", f"HEAD...{upstream}"]) if upstream else None
        ahead: int | None = None
        behind: int | None = None
        if counts:
            parts = counts.split()
            if len(parts) == 2:
                try:
                    ahead = int(parts[0])
                    behind = int(parts[1])
                except ValueError:
                    ahead = behind = None
        dirty_result = self._run_git(["status", "--porcelain"])
        dirty = dirty_result.returncode == 0 and bool((dirty_result.stdout or "").strip())
        status.update(
            {
                "branch": branch,
                "upstream": upstream,
                "local_sha": local_sha,
                "remote_sha": remote_sha,
                "ahead": ahead,
                "behind": behind,
                "dirty": dirty,
                "update_available": bool(behind and behind > 0),
            }
        )
        if dirty_result.returncode != 0:
            status["dirty_error"] = self._redact_update_text(dirty_result.stderr or dirty_result.stdout)
        return status

    def _updater_status(self) -> dict[str, Any]:
        install_root = self._install_root()
        script = install_root / "scripts" / "update.sh"
        status: dict[str, Any] = {
            "unit": "hexe-updater.service",
            "script_path": str(script),
            "script_exists": script.exists(),
            "script_executable": os.access(script, os.X_OK),
            "systemctl_available": shutil.which("systemctl") is not None,
            "unit_loaded": False,
            "active_state": "unknown",
            "sub_state": "unknown",
            "result": None,
            "exec_main_status": None,
        }
        if not status["systemctl_available"]:
            status["error"] = "systemctl_not_found"
            return status
        try:
            result = self._run_systemctl_user(
                [
                    "show",
                    "hexe-updater.service",
                    "--property=LoadState,ActiveState,SubState,Result,ExecMainStatus,InactiveEnterTimestamp",
                    "--no-page",
                ],
            )
        except Exception as exc:
            status["error"] = self._redact_update_text(exc)
            return status
        if result.returncode != 0:
            status["error"] = self._redact_update_text(result.stderr or result.stdout) or f"systemctl_exit_{result.returncode}"
            return status
        props: dict[str, str] = {}
        for line in (result.stdout or "").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            props[key] = value
        status.update(
            {
                "unit_loaded": props.get("LoadState") == "loaded",
                "load_state": props.get("LoadState"),
                "active_state": props.get("ActiveState") or "unknown",
                "sub_state": props.get("SubState") or "unknown",
                "result": props.get("Result") or None,
                "exec_main_status": props.get("ExecMainStatus") or None,
                "inactive_enter_timestamp": props.get("InactiveEnterTimestamp") or None,
            }
        )
        return status

    def _finalize_update_state(self, state: dict[str, Any], updater: dict[str, Any]) -> dict[str, Any]:
        current = dict(state.get("current_update") or {}) if isinstance(state.get("current_update"), dict) else None
        if not current:
            return state
        active_state = str(updater.get("active_state") or "").strip().lower()
        if active_state in {"activating", "active", "reloading"}:
            current["state"] = "running"
            current["updated_at"] = self._now_iso()
            state["current_update"] = current
            return state
        if str(current.get("state") or "").lower() not in {"starting", "running"}:
            return state
        result = str(updater.get("result") or "").strip().lower()
        exit_status = str(updater.get("exec_main_status") or "").strip()
        succeeded = result in {"success", ""} and exit_status in {"", "0"}
        finished = {
            **current,
            "state": "succeeded" if succeeded else "failed",
            "finished_at": self._now_iso(),
            "result": updater.get("result"),
            "exec_main_status": updater.get("exec_main_status"),
        }
        state.pop("current_update", None)
        state["last_update"] = finished
        self._write_update_state(state)
        return state

    def supervisor_update_status(self) -> SupervisorUpdateStatusSummary:
        git = self._git_update_status()
        updater = self._updater_status()
        state = self._finalize_update_state(self._read_update_state(), updater)
        unsupported: dict[str, str] = {}
        supported_modes: list[str] = []
        if not bool(git.get("is_git_checkout")):
            unsupported["git"] = "source_path_is_not_git_checkout"
        elif not bool(updater.get("script_exists")):
            unsupported["git"] = "updater_script_missing"
        elif not bool(updater.get("unit_loaded")):
            unsupported["git"] = "updater_unit_missing"
        else:
            supported_modes.append("git")
        unsupported["core_host"] = "core_host_package_mode_not_implemented"
        current_update = dict(state.get("current_update") or {}) if isinstance(state.get("current_update"), dict) else None
        last_update = dict(state.get("last_update") or {}) if isinstance(state.get("last_update"), dict) else None
        update_state = str((current_update or last_update or {}).get("state") or "idle")
        return SupervisorUpdateStatusSummary(
            supervisor_id=self._supervisor_id(),
            reported_version=self._supervisor_version(),
            install_root=str(self._install_root()),
            source_path=str(self._install_root()),
            source_is_git_checkout=bool(git.get("is_git_checkout")),
            supported_modes=supported_modes,
            unsupported_reasons=unsupported,
            git=git,
            updater=updater,
            update_state=update_state,
            current_update=current_update,
            last_update=last_update,
            updated_at=self._now_iso(),
        )

    def start_supervisor_update(self, body: SupervisorUpdateStartRequest) -> SupervisorUpdateStartResult:
        status = self.supervisor_update_status()
        state = self._read_update_state()
        current = dict(state.get("current_update") or {}) if isinstance(state.get("current_update"), dict) else None
        last = dict(state.get("last_update") or {}) if isinstance(state.get("last_update"), dict) else None
        if current and current.get("idempotency_key") == body.idempotency_key:
            return SupervisorUpdateStartResult(
                accepted=True,
                state=str(current.get("state") or status.update_state),
                source_mode=body.source_mode,
                idempotency_key=body.idempotency_key,
                message="update_request_already_accepted",
                status=status,
            )
        if last and last.get("idempotency_key") == body.idempotency_key:
            return SupervisorUpdateStartResult(
                accepted=False,
                state=str(last.get("state") or status.update_state),
                source_mode=body.source_mode,
                idempotency_key=body.idempotency_key,
                message="update_request_already_finished",
                status=status,
            )
        if current:
            raise HTTPException(status_code=409, detail={"error": "supervisor_update_already_running"})
        if body.source_mode == "core_host":
            raise HTTPException(status_code=409, detail={"error": "supervisor_update_mode_not_configured", "mode": "core_host"})
        if body.source_mode not in status.supported_modes:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "supervisor_update_mode_unsupported",
                    "mode": body.source_mode,
                    "reason": status.unsupported_reasons.get(body.source_mode),
                },
            )
        if body.service_update:
            raise HTTPException(status_code=409, detail={"error": "supervisor_service_update_option_not_supported"})
        started_at = self._now_iso()
        attempt = {
            "state": "starting",
            "source_mode": body.source_mode,
            "idempotency_key": body.idempotency_key,
            "service_update": body.service_update,
            "requested_at": started_at,
            "updated_at": started_at,
            "command": ["systemctl", "--user", "start", "hexe-updater.service"],
        }
        state["current_update"] = attempt
        self._write_update_state(state)
        try:
            result = self._run_systemctl_user(["start", "hexe-updater.service"])
        except Exception as exc:
            error = self._redact_update_text(exc) or type(exc).__name__
            failed = {**attempt, "state": "failed", "finished_at": self._now_iso(), "error": error}
            state.pop("current_update", None)
            state["last_update"] = failed
            self._write_update_state(state)
            raise HTTPException(status_code=500, detail={"error": "supervisor_update_start_failed", "message": error}) from None
        if result.returncode != 0:
            error = self._redact_update_text(result.stderr or result.stdout) or f"systemctl_exit_{result.returncode}"
            failed = {
                **attempt,
                "state": "failed",
                "finished_at": self._now_iso(),
                "exit_code": result.returncode,
                "error": error,
            }
            state.pop("current_update", None)
            state["last_update"] = failed
            self._write_update_state(state)
            raise HTTPException(status_code=500, detail={"error": "supervisor_update_start_failed", "message": error}) from None
        accepted_status = self.supervisor_update_status()
        return SupervisorUpdateStartResult(
            accepted=True,
            state=accepted_status.update_state,
            source_mode=body.source_mode,
            idempotency_key=body.idempotency_key,
            message="supervisor_update_started",
            status=accepted_status,
        )

    def _bluetooth_ensure_powered_enabled(self) -> bool:
        raw = str(getenv("HEXE_BLUETOOTH_ENSURE_POWERED", "")).strip().lower()
        if not raw:
            return True
        return raw in {"1", "true", "yes", "on"}

    def _collect_bluetooth_adapters(self) -> list[dict[str, Any]]:
        adapters: dict[str, dict[str, Any]] = {}
        for path in sorted(Path("/sys/class/bluetooth").glob("hci*")):
            adapters[path.name] = {
                "adapter": path.name,
                "present": True,
                "powered": False,
                "source": "sysfs",
            }
        if shutil.which("hciconfig"):
            try:
                result = subprocess.run(["hciconfig", "-a"], capture_output=True, text=True, timeout=2.0, check=False)
            except Exception:
                result = None
            if result is not None and result.returncode == 0:
                current: dict[str, Any] | None = None
                for line in (result.stdout or "").splitlines():
                    if line.startswith("hci") and ":" in line:
                        adapter = line.split(":", 1)[0].strip()
                        current = adapters.setdefault(
                            adapter,
                            {
                                "adapter": adapter,
                                "present": True,
                                "powered": False,
                            },
                        )
                        current["source"] = "hciconfig"
                        current["bus"] = line.split("Bus:", 1)[1].strip() if "Bus:" in line else None
                        continue
                    if current is None:
                        continue
                    text = line.strip()
                    if text.startswith("BD Address:"):
                        current["address"] = text.split("BD Address:", 1)[1].split()[0]
                    if text == "UP" or text.startswith("UP "):
                        current["powered"] = True
                    if text == "DOWN" or text.startswith("DOWN "):
                        current["powered"] = False
        return list(adapters.values())

    def _ensure_bluetooth_powered(self, adapters: list[dict[str, Any]]) -> None:
        if not self._bluetooth_ensure_powered_enabled() or not adapters:
            return
        if any(bool(item.get("powered")) for item in adapters):
            self._bluetooth_power_error = None
            return
        now = time.time()
        retry_s = 60.0
        raw_retry = str(getenv("HEXE_BLUETOOTH_POWER_RETRY_S", "")).strip()
        if raw_retry:
            try:
                retry_s = max(5.0, float(raw_retry))
            except Exception:
                retry_s = 60.0
        if now - self._bluetooth_power_last_attempt_s < retry_s:
            return
        self._bluetooth_power_last_attempt_s = now
        errors: list[str] = []
        if shutil.which("bluetoothctl"):
            result = subprocess.run(["bluetoothctl", "power", "on"], capture_output=True, text=True, timeout=5.0, check=False)
            if result.returncode != 0:
                errors.append((result.stderr or result.stdout or f"bluetoothctl exited {result.returncode}").strip())
        if shutil.which("hciconfig"):
            for item in adapters:
                adapter = str(item.get("adapter") or "").strip()
                if not adapter:
                    continue
                result = subprocess.run(["hciconfig", adapter, "up"], capture_output=True, text=True, timeout=5.0, check=False)
                if result.returncode != 0:
                    errors.append((result.stderr or result.stdout or f"hciconfig {adapter} exited {result.returncode}").strip())
        self._bluetooth_power_error = "; ".join(value for value in errors if value) or None

    def _bluetooth_summary(self) -> dict[str, Any]:
        adapter_list = self._collect_bluetooth_adapters()
        powered = any(bool(item.get("powered")) for item in adapter_list)
        if adapter_list and not powered and self._bluetooth_ensure_powered_enabled():
            self._ensure_bluetooth_powered(adapter_list)
            adapter_list = self._collect_bluetooth_adapters()
            powered = any(bool(item.get("powered")) for item in adapter_list)
        return {
            "bluetooth_present": bool(adapter_list),
            "bluetooth_powered": powered,
            "bluetooth_ensure_powered": self._bluetooth_ensure_powered_enabled(),
            "bluetooth_power_error": None if powered else self._bluetooth_power_error,
            "bluetooth_adapters": adapter_list,
        }

    def _hardware_validation_url(self) -> str | None:
        configured = str(getenv("HEXE_HARDWARE_LEASE_VALIDATE_URL") or "").strip()
        if configured:
            return configured
        core_url = str(getenv("HEXE_SUPERVISOR_CORE_URL") or "").strip().rstrip("/")
        if core_url:
            return f"{core_url}/api/system/hardware/leases/validate"
        return None

    def _hardware_validation_headers(self) -> dict[str, str]:
        token = str(getenv("HEXE_SUPERVISOR_CORE_TOKEN") or getenv("HEXE_ADMIN_TOKEN") or "").strip()
        kind = str(getenv("HEXE_SUPERVISOR_CORE_TOKEN_KIND") or "").strip().lower()
        if not kind:
            kind = "supervisor" if token.startswith("hexe_sup_report_") else "admin"
        if kind == "supervisor":
            return {"X-Supervisor-Id": self._supervisor_id(), "X-Supervisor-Token": token}
        return {"X-Admin-Token": token}

    def _validate_bluetooth_lease(self, body: SupervisorBluetoothLeaseRequest, *, operation: str) -> dict[str, Any]:
        payload = {
            "node_id": str(body.node_id or "").strip(),
            "lease_token": str(body.lease_token or "").strip(),
            "resource_type": "bluetooth",
            "operation": operation,
            "supervisor_id": self._supervisor_id(),
            "adapter": str(body.adapter or "").strip() or None,
        }
        requested_provisioning = self._provisioning_context_for_request(body)
        if operation == "ble.provision_wifi":
            payload["provisioning"] = requested_provisioning
        validation_url = self._hardware_validation_url()
        if validation_url:
            try:
                response = httpx.post(
                    validation_url,
                    json=payload,
                    headers=self._hardware_validation_headers(),
                    timeout=5.0,
                )
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail={"error": "hardware_lease_validation_unavailable", "message": str(exc)}) from None
            if response.status_code >= 400:
                raise HTTPException(status_code=502, detail={"error": "hardware_lease_validation_failed", "status_code": response.status_code})
            try:
                result = response.json()
            except ValueError:
                raise HTTPException(status_code=502, detail={"error": "hardware_lease_validation_invalid_json"}) from None
            if not isinstance(result, dict) or not bool(result.get("valid")):
                error = str(result.get("error") if isinstance(result, dict) else "hardware_lease_invalid")
                raise HTTPException(status_code=403, detail={"error": error or "hardware_lease_invalid"})
            result["revocation_check"] = "core"
            return result

        secret = hardware_lease_secret()
        if not secret:
            raise HTTPException(status_code=503, detail={"error": "hardware_lease_secret_unconfigured"})
        try:
            _header, claims_payload = verify_hs256(body.lease_token, [{"kid": "hardware-v1", "secret": secret}])
            claims = validate_claims(
                claims_payload,
                audience=HARDWARE_LEASE_AUDIENCE,
                required_scopes=[f"hardware.bluetooth.{operation}"],
            )
        except ServiceTokenError as exc:
            raise HTTPException(status_code=403, detail={"error": str(exc)}) from None
        if str(claims_payload.get("node_id") or claims.sub).strip() != payload["node_id"]:
            raise HTTPException(status_code=403, detail={"error": "hardware_access_node_mismatch"})
        if str(claims_payload.get("resource_type") or "").strip() != "bluetooth":
            raise HTTPException(status_code=403, detail={"error": "hardware_access_resource_mismatch"})
        if str(claims_payload.get("operation") or "").strip() != operation:
            raise HTTPException(status_code=403, detail={"error": "hardware_access_operation_mismatch"})
        token_supervisor_id = str(claims_payload.get("supervisor_id") or "").strip()
        if token_supervisor_id and token_supervisor_id != self._supervisor_id():
            raise HTTPException(status_code=403, detail={"error": "hardware_access_supervisor_mismatch"})
        token_adapter = str(claims_payload.get("adapter") or "").strip()
        requested_adapter = str(body.adapter or "").strip()
        if token_adapter and requested_adapter and token_adapter != requested_adapter:
            raise HTTPException(status_code=403, detail={"error": "hardware_access_adapter_mismatch"})
        if operation == "ble.provision_wifi":
            token_provisioning = claims_payload.get("provisioning") if isinstance(claims_payload.get("provisioning"), dict) else None
            if not token_provisioning or not requested_provisioning:
                raise HTTPException(status_code=403, detail={"error": "hardware_access_provisioning_context_required"})
            for key in ("contract_version", "onboarding_session_id", "target_node_id", "node_profile_id", "payload_schema_id"):
                if str(token_provisioning.get(key) or "").strip() != str(requested_provisioning.get(key) or "").strip():
                    raise HTTPException(status_code=403, detail={"error": f"hardware_access_provisioning_{key}_mismatch"})
            for key in ("schema_version", "endpoint_ephemeral_public_key", "sequence"):
                if str(token_provisioning.get(key) or "").strip() != str(requested_provisioning.get(key) or "").strip():
                    raise HTTPException(status_code=403, detail={"error": f"hardware_access_provisioning_{key}_mismatch"})
            if str(token_provisioning.get("expires_at") or "").strip() and str(token_provisioning.get("expires_at") or "").strip() != str(
                requested_provisioning.get("expires_at") or ""
            ).strip():
                raise HTTPException(status_code=403, detail={"error": "hardware_access_provisioning_expires_at_mismatch"})
            if str(token_provisioning.get("pairing_nonce") or "").strip() and str(token_provisioning.get("pairing_nonce") or "").strip() != str(
                requested_provisioning.get("pairing_nonce") or ""
            ).strip():
                raise HTTPException(status_code=403, detail={"error": "hardware_access_provisioning_pairing_nonce_mismatch"})
            if str(token_provisioning.get("claim_code_ref") or "").strip() and str(token_provisioning.get("claim_code_ref") or "").strip() != str(
                requested_provisioning.get("claim_code_ref") or ""
            ).strip():
                raise HTTPException(status_code=403, detail={"error": "hardware_access_provisioning_claim_code_ref_mismatch"})
        return {"ok": True, "valid": True, "claims": claims.to_dict(), "revocation_check": "local_token_only"}

    @staticmethod
    def _provisioning_context_for_request(body: SupervisorBluetoothLeaseRequest) -> dict[str, Any] | None:
        required = ("contract_version", "onboarding_session_id", "target_node_id", "node_profile_id", "payload_schema_id")
        if not all(hasattr(body, key) for key in required):
            return None
        return {
            "contract_version": str(getattr(body, "contract_version") or "").strip(),
            "onboarding_session_id": str(getattr(body, "onboarding_session_id") or "").strip(),
            "target_node_id": str(getattr(body, "target_node_id") or "").strip(),
            "node_profile_id": str(getattr(body, "node_profile_id") or "").strip(),
            "payload_schema_id": str(getattr(body, "payload_schema_id") or "").strip(),
            "schema_version": str(getattr(body, "schema_version", None) or "").strip(),
            "endpoint_ephemeral_public_key": str(getattr(body, "endpoint_ephemeral_public_key", None) or "").strip(),
            "pairing_nonce": str(getattr(body, "pairing_nonce", None) or "").strip() or None,
            "claim_code_ref": str(getattr(body, "claim_code_ref", None) or "").strip() or None,
            "sequence": int(getattr(body, "sequence", 1) or 1),
            "expires_at": str(getattr(body, "expires_at", None) or "").strip() or None,
        }

    @staticmethod
    def _redacted_voice_payload(body: SupervisorBluetoothProvisionWifiRequest) -> dict[str, Any]:
        payload = body.credential_payload.model_dump(mode="json")
        if payload.get("wifi_password") is not None:
            payload["wifi_password"] = "[REDACTED]"
        return payload

    def _record_ble_provisioning_event(self, event: str, body: SupervisorBluetoothProvisionWifiRequest, **details: Any) -> None:
        self._ble_provisioning_events.append(
            {
                "event": event,
                "at": self._now_iso(),
                "node_id": body.node_id,
                "target_node_id": body.target_node_id,
                "onboarding_session_id": body.onboarding_session_id,
                "node_profile_id": body.node_profile_id,
                "payload_schema_id": body.payload_schema_id,
                **details,
            }
        )

    @staticmethod
    def _b64url_encode(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _b64url_decode(value: str) -> bytes:
        text = str(value or "").strip()
        padding = "=" * (-len(text) % 4)
        return base64.urlsafe_b64decode(text + padding)

    @staticmethod
    def _json_bytes(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _redact_message(
        text: object,
        body: SupervisorBluetoothProvisionWifiRequest | None = None,
        envelope: dict[str, Any] | None = None,
    ) -> str:
        value = str(text or "")
        replacements = {"[REDACTED]", str(getattr(body, "lease_token", "") or ""), str(getattr(body, "endpoint_ephemeral_public_key", "") or "")}
        if body is not None:
            credential_payload = body.credential_payload.model_dump(mode="json")
            replacements.update(str(item) for item in credential_payload.values() if item)
            replacements.update(
                str(item)
                for item in (
                    body.claim_code_ref,
                    body.pairing_nonce,
                    body.onboarding_session_id,
                )
                if item
            )
        if isinstance(envelope, dict):
            replacements.update(str(envelope.get(item) or "") for item in ("ciphertext", "tag", "nonce", "aad"))
        for secret in sorted((item for item in replacements if item), key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        return value

    @staticmethod
    def _validate_provisioning_expiry(expires_at: str) -> None:
        try:
            expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=422, detail={"error": "provisioning_expires_at_invalid"}) from None
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail={"error": "provisioning_envelope_expired"})

    def _provisioning_expires_at(self, body: SupervisorBluetoothProvisionWifiRequest, validation: dict[str, Any]) -> str:
        if body.expires_at:
            return str(body.expires_at)
        lease = validation.get("lease") if isinstance(validation.get("lease"), dict) else {}
        lease_expires_at = str(lease.get("expires_at") or "").strip()
        if lease_expires_at:
            return lease_expires_at
        claims = validation.get("claims") if isinstance(validation.get("claims"), dict) else {}
        exp = claims.get("exp")
        if isinstance(exp, int):
            return datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _build_provisioning_envelope(
        self,
        body: SupervisorBluetoothProvisionWifiRequest,
        *,
        validation: dict[str, Any],
    ) -> dict[str, Any]:
        expires_at = self._provisioning_expires_at(body, validation)
        self._validate_provisioning_expiry(expires_at)
        pairing_nonce = str(body.pairing_nonce or "").strip()
        if not pairing_nonce:
            raise HTTPException(status_code=422, detail={"error": "pairing_nonce_required_for_encrypted_envelope"})
        try:
            endpoint_public_key = x25519.X25519PublicKey.from_public_bytes(self._b64url_decode(body.endpoint_ephemeral_public_key))
        except Exception:
            raise HTTPException(status_code=422, detail={"error": "endpoint_ephemeral_public_key_invalid"}) from None

        supervisor_private_key = x25519.X25519PrivateKey.generate()
        supervisor_public_key = supervisor_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        shared_secret = supervisor_private_key.exchange(endpoint_public_key)
        salt = self._json_bytes(
            {
                "contract_version": BLE_PROVISIONING_CONTRACT_VERSION,
                "schema_version": BLE_PROVISIONING_ENVELOPE_SCHEMA_VERSION,
                "onboarding_session_id": body.onboarding_session_id,
                "target_node_id": body.target_node_id,
                "pairing_nonce": pairing_nonce,
            }
        )
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=f"hexe:{BLE_PROVISIONING_KEY_AGREEMENT}:ble.provision_wifi".encode("ascii"),
        ).derive(shared_secret)
        aad_payload = {
            "schema_version": BLE_PROVISIONING_ENVELOPE_SCHEMA_VERSION,
            "payload_schema_id": body.payload_schema_id,
            "contract_version": BLE_PROVISIONING_CONTRACT_VERSION,
            "onboarding_session_id": body.onboarding_session_id,
            "target_node_id": body.target_node_id,
            "pairing_nonce": pairing_nonce,
            "sequence": body.sequence,
            "expires_at": expires_at,
            "algorithm": BLE_PROVISIONING_ENCRYPTION_ALGORITHM,
            "key_agreement": BLE_PROVISIONING_KEY_AGREEMENT,
        }
        aad = self._json_bytes(aad_payload)
        plaintext = self._json_bytes(
            {
                "payload_schema_id": body.payload_schema_id,
                "credential_payload": body.credential_payload.model_dump(mode="json"),
            }
        )
        nonce = os.urandom(12)
        encrypted = AESGCM(key).encrypt(nonce, plaintext, aad)
        ciphertext, tag = encrypted[:-16], encrypted[-16:]
        key_id = hashlib.sha256(
            self._json_bytes(
                {
                    "endpoint_ephemeral_public_key": body.endpoint_ephemeral_public_key,
                    "supervisor_ephemeral_public_key": self._b64url_encode(supervisor_public_key),
                    "onboarding_session_id": body.onboarding_session_id,
                    "target_node_id": body.target_node_id,
                    "sequence": body.sequence,
                }
            )
        ).hexdigest()
        return {
            **aad_payload,
            "key_id": key_id,
            "supervisor_ephemeral_public_key": self._b64url_encode(supervisor_public_key),
            "nonce": self._b64url_encode(nonce),
            "aad": self._b64url_encode(aad),
            "ciphertext": self._b64url_encode(ciphertext),
            "tag": self._b64url_encode(tag),
        }

    @staticmethod
    def _parse_bluetoothctl_devices(output: str) -> list[dict[str, Any]]:
        devices: dict[str, dict[str, Any]] = {}
        for line in (output or "").splitlines():
            text = line.strip()
            if not text:
                continue
            if text.startswith("["):
                parts = text.split("Device ", 1)
                if len(parts) == 2:
                    text = "Device " + parts[1]
            if not text.startswith("Device "):
                continue
            parts = text.split(maxsplit=2)
            if len(parts) < 2:
                continue
            address = parts[1].strip()
            name = parts[2].strip() if len(parts) > 2 else None
            if ":" not in address:
                continue
            devices[address] = {"address": address, "name": name, "transport": "ble"}
        return list(devices.values())

    @staticmethod
    def _normalize_ble_uuid(value: object) -> str | None:
        text = str(value or "").strip().lower()
        if not text:
            return None
        if text.startswith("urn:uuid:"):
            text = text.removeprefix("urn:uuid:")
        return text.strip("{}") or None

    @classmethod
    def _parse_bluetoothctl_info(cls, output: str) -> dict[str, Any]:
        result: dict[str, Any] = {"uuids": []}
        uuids: set[str] = set()
        for line in (output or "").splitlines():
            text = line.strip()
            if text.startswith("Name: "):
                result["name"] = text.split("Name: ", 1)[1].strip()
                continue
            if text.startswith("Alias: "):
                result["alias"] = text.split("Alias: ", 1)[1].strip()
                continue
            if not text.startswith("UUID: "):
                continue
            raw_uuid = text.split("UUID: ", 1)[1].strip()
            if "(" in raw_uuid and raw_uuid.endswith(")"):
                raw_uuid = raw_uuid.rsplit("(", 1)[1].rstrip(")").strip()
            uuid = cls._normalize_ble_uuid(raw_uuid)
            if uuid:
                uuids.add(uuid)
        result["uuids"] = sorted(uuids)
        return result

    def _enrich_bluetoothctl_devices(
        self,
        devices: list[dict[str, Any]],
        service_uuid: str | None,
    ) -> list[dict[str, Any]]:
        requested_uuid = self._normalize_ble_uuid(service_uuid)
        if not requested_uuid:
            return devices
        enriched: list[dict[str, Any]] = []
        for device in devices:
            address = str(device.get("address") or "").strip()
            item = dict(device)
            info: dict[str, Any] = {}
            if address:
                try:
                    result = subprocess.run(
                        ["bluetoothctl", "info", address],
                        capture_output=True,
                        text=True,
                        timeout=5.0,
                        check=False,
                    )
                    if result.returncode == 0:
                        info = self._parse_bluetoothctl_info(
                            (result.stdout or "") + "\n" + (result.stderr or "")
                        )
                except Exception:
                    info = {}
            if info.get("name") and (
                not item.get("name") or str(item.get("name")) == address.replace(":", "-")
            ):
                item["name"] = info["name"]
            if info.get("alias"):
                item["alias"] = info["alias"]
            uuids = [value for value in info.get("uuids", []) if isinstance(value, str)]
            if uuids:
                item["uuids"] = uuids
            matched = requested_uuid in uuids
            item["service_uuid_match"] = matched
            if matched:
                item["matched_service_uuid"] = requested_uuid
            enriched.append(item)
        return enriched

    def _bluetooth_adapter_for_request(self, adapter: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        summary = self._bluetooth_summary()
        adapters = list(summary.get("bluetooth_adapters") or [])
        if not adapters:
            raise HTTPException(status_code=404, detail={"error": "bluetooth_unavailable"})
        requested_adapter = str(adapter or "").strip()
        if requested_adapter:
            matched = next((item for item in adapters if str(item.get("adapter") or "").strip() == requested_adapter), None)
            if matched is None:
                raise HTTPException(status_code=404, detail={"error": "bluetooth_adapter_not_found"})
            return matched, adapters
        selected = next((item for item in adapters if bool(item.get("powered"))), adapters[0])
        return selected, adapters

    def bluetooth_ble_status(self, body: SupervisorBluetoothLeaseRequest) -> dict[str, Any]:
        validation = self._validate_bluetooth_lease(body, operation="ble.status")
        adapter, adapters = self._bluetooth_adapter_for_request(body.adapter)
        return {
            "ok": True,
            "operation": "ble.status",
            "node_id": body.node_id,
            "supervisor_id": self._supervisor_id(),
            "adapter": adapter,
            "adapters": adapters,
            "revocation_check": validation.get("revocation_check"),
        }

    def bluetooth_ble_scan(self, body: SupervisorBluetoothBleScanRequest) -> dict[str, Any]:
        validation = self._validate_bluetooth_lease(body, operation="ble.scan")
        adapter, adapters = self._bluetooth_adapter_for_request(body.adapter)
        if not shutil.which("bluetoothctl"):
            return {
                "ok": False,
                "operation": "ble.scan",
                "error": "bluetoothctl_unavailable",
                "node_id": body.node_id,
                "supervisor_id": self._supervisor_id(),
                "adapter": adapter,
                "adapters": adapters,
                "devices": [],
                "revocation_check": validation.get("revocation_check"),
            }
        scan_seconds = max(1, min(int(body.scan_seconds or 5), 60))
        scan_output = ""
        try:
            scan = subprocess.run(
                ["bluetoothctl", "--timeout", str(scan_seconds), "scan", "le"],
                capture_output=True,
                text=True,
                timeout=scan_seconds + 3.0,
                check=False,
            )
            scan_output = (scan.stdout or "") + "\n" + (scan.stderr or "")
        except Exception as exc:
            scan_output = str(exc)
        try:
            devices = subprocess.run(
                ["bluetoothctl", "devices"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            devices_output = (devices.stdout or "") + "\n" + (devices.stderr or "")
        except Exception:
            devices_output = ""
        service_uuid = self._normalize_ble_uuid(body.service_uuid)
        parsed_devices = self._parse_bluetoothctl_devices(scan_output + "\n" + devices_output)
        devices = self._enrich_bluetoothctl_devices(parsed_devices, service_uuid)
        matching_devices = [item for item in devices if item.get("service_uuid_match")]
        return {
            "ok": True,
            "operation": "ble.scan",
            "node_id": body.node_id,
            "supervisor_id": self._supervisor_id(),
            "adapter": adapter,
            "adapters": adapters,
            "scan_seconds": scan_seconds,
            "scan_transport": "le",
            "service_uuid": service_uuid,
            "devices": devices,
            "matching_devices": matching_devices,
            "revocation_check": validation.get("revocation_check"),
        }

    def bluetooth_ble_provision_wifi(self, body: SupervisorBluetoothProvisionWifiRequest) -> dict[str, Any]:
        validation = self._validate_bluetooth_lease(body, operation="ble.provision_wifi")
        adapter, adapters = self._bluetooth_adapter_for_request(body.adapter)
        provisioning = self._provisioning_context_for_request(body) or {}
        envelope = self._build_provisioning_envelope(body, validation=validation)
        self._record_ble_provisioning_event(
            "provision_wifi_attempted",
            body,
            adapter=adapter.get("adapter"),
            envelope_schema_version=envelope["schema_version"],
            sequence=envelope["sequence"],
            envelope_key_id=envelope["key_id"],
        )
        try:
            result = self._ble_provisioning_backend.provision_wifi(
                adapter=adapter,
                validation=validation,
                envelope=envelope,
                target_address=body.target_address,
                timeout_s=body.timeout_s,
            )
        except Exception as exc:
            result = {
                "ok": False,
                "status": "failed",
                "ack": False,
                "error": "gatt_backend_failed",
                "message": self._redact_message(str(exc), body, envelope),
            }
        ok = bool(result.get("ok")) if isinstance(result, dict) else False
        status = str(result.get("status") or ("completed" if ok else "failed")) if isinstance(result, dict) else "failed"
        error = str(result.get("error") or "") if isinstance(result, dict) else "gatt_backend_failed"
        message = self._redact_message(result.get("message"), body, envelope) if isinstance(result, dict) else None
        self._record_ble_provisioning_event(
            "provision_wifi_completed" if ok else "provision_wifi_rejected",
            body,
            status=status,
            error=error or None,
        )
        return {
            "ok": ok,
            "operation": "ble.provision_wifi",
            "node_id": body.node_id,
            "supervisor_id": self._supervisor_id(),
            "adapter": adapter,
            "adapters": adapters,
            "target_address": body.target_address,
            "provisioning": provisioning,
            "credential_payload": self._redacted_voice_payload(body),
            "provisioning_envelope": {
                "schema_version": envelope["schema_version"],
                "payload_schema_id": envelope["payload_schema_id"],
                "contract_version": envelope["contract_version"],
                "sequence": envelope["sequence"],
                "expires_at": envelope["expires_at"],
                "algorithm": envelope["algorithm"],
                "key_agreement": envelope["key_agreement"],
                "key_id": envelope["key_id"],
                "ciphertext": "[REDACTED]",
                "tag": "[REDACTED]",
            },
            "status": status,
            "ack": bool(result.get("ack", ok)) if isinstance(result, dict) else False,
            "error": (error or None),
            "message": message,
            "revocation_check": validation.get("revocation_check"),
        }

    def _network_transport_summary(self) -> dict[str, Any]:
        interface = None
        try:
            result = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=2.0, check=False)
            if result.returncode == 0:
                for line in (result.stdout or "").splitlines():
                    parts = line.split()
                    if "dev" in parts:
                        interface = parts[parts.index("dev") + 1]
                        break
        except Exception:
            interface = None
        if not interface:
            return {"network_primary_type": "unknown"}

        iface_path = Path("/sys/class/net") / interface
        link_type = "unknown"
        if interface == "lo":
            link_type = "loopback"
        elif (iface_path / "wireless").exists():
            link_type = "wifi"
        else:
            try:
                type_value = (iface_path / "type").read_text(encoding="utf-8").strip()
            except Exception:
                type_value = ""
            if type_value == "1":
                link_type = "ethernet"

        speed_mbps = None
        try:
            raw_speed = int((iface_path / "speed").read_text(encoding="utf-8").strip())
            if raw_speed >= 0:
                speed_mbps = raw_speed
        except Exception:
            speed_mbps = None

        wifi_signal_percent = None
        if link_type == "wifi":
            try:
                for line in Path("/proc/net/wireless").read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith(f"{interface}:"):
                        values = line.split()
                        quality = float(values[2].rstrip("."))
                        wifi_signal_percent = max(0.0, min(100.0, (quality / 70.0) * 100.0))
                        break
            except Exception:
                wifi_signal_percent = None

        return {
            "network_primary_interface": interface,
            "network_primary_type": link_type,
            "network_link_speed_mbps": speed_mbps,
            "wifi_signal_percent": wifi_signal_percent,
        }

    def _internet_summary(self) -> dict[str, Any]:
        host = str(getenv("HEXE_SUPERVISOR_INTERNET_CHECK_HOST", "1.1.1.1")).strip() or "1.1.1.1"
        raw_port = str(getenv("HEXE_SUPERVISOR_INTERNET_CHECK_PORT", "53")).strip()
        try:
            port = int(raw_port)
        except Exception:
            port = 53
        try:
            with socket.create_connection((host, port), timeout=2.0):
                return {"internet_reachable": True, "internet_check_error": None}
        except Exception as exc:
            return {"internet_reachable": False, "internet_check_error": str(exc)}

    def _host_resources(self) -> HostResourceSummary:
        stats = collect_system_stats(api_metrics=None)
        root_disk = stats.disks.get("/")
        gpu_summary = self._resource_monitor.gpu_summary()
        bluetooth_summary = self._bluetooth_summary()
        network_transport = self._network_transport_summary()
        internet_summary = self._internet_summary()
        net_total = stats.net.total
        net_rate = stats.net.total_rate
        summary = HostResourceSummary(
            uptime_s=stats.uptime_s,
            load_1m=stats.load.load1,
            load_5m=stats.load.load5,
            load_15m=stats.load.load15,
            cpu_percent_total=stats.cpu.percent_total,
            cpu_cores_logical=stats.cpu.cores_logical,
            memory_total_bytes=stats.mem.total,
            memory_available_bytes=stats.mem.available,
            memory_percent=stats.mem.percent,
            root_disk_total_bytes=root_disk.total if root_disk is not None else None,
            root_disk_free_bytes=root_disk.free if root_disk is not None else None,
            root_disk_percent=root_disk.percent if root_disk is not None else None,
            gpu_count=int(gpu_summary.get("gpu_count") or 0),
            gpu_utilization_percent=(
                float(gpu_summary["gpu_utilization_percent"])
                if isinstance(gpu_summary.get("gpu_utilization_percent"), int | float)
                else None
            ),
            gpu_memory_percent=(
                float(gpu_summary["gpu_memory_percent"])
                if isinstance(gpu_summary.get("gpu_memory_percent"), int | float)
                else None
            ),
            gpu_devices=list(gpu_summary.get("gpu_devices") or []),
            cuda_available=bool(gpu_summary.get("cuda_available")),
            cuda_version=str(gpu_summary["cuda_version"]) if gpu_summary.get("cuda_version") else None,
            bluetooth_present=bool(bluetooth_summary.get("bluetooth_present")),
            bluetooth_powered=bool(bluetooth_summary.get("bluetooth_powered")),
            bluetooth_ensure_powered=bool(bluetooth_summary.get("bluetooth_ensure_powered")),
            bluetooth_power_error=str(bluetooth_summary["bluetooth_power_error"])
            if bluetooth_summary.get("bluetooth_power_error")
            else None,
            bluetooth_adapters=list(bluetooth_summary.get("bluetooth_adapters") or []),
            network_rx_Bps=net_rate.rx_Bps if net_rate is not None else None,
            network_tx_Bps=net_rate.tx_Bps if net_rate is not None else None,
            network_bytes_recv=net_total.bytes_recv,
            network_bytes_sent=net_total.bytes_sent,
            network_errin=net_total.errin,
            network_errout=net_total.errout,
            network_dropin=net_total.dropin,
            network_dropout=net_total.dropout,
            network_primary_interface=str(network_transport["network_primary_interface"])
            if network_transport.get("network_primary_interface")
            else None,
            network_primary_type=str(network_transport.get("network_primary_type") or "unknown"),
            network_link_speed_mbps=(
                int(network_transport["network_link_speed_mbps"])
                if isinstance(network_transport.get("network_link_speed_mbps"), int)
                else None
            ),
            wifi_signal_percent=(
                float(network_transport["wifi_signal_percent"])
                if isinstance(network_transport.get("wifi_signal_percent"), int | float)
                else None
            ),
            internet_reachable=(
                bool(internet_summary["internet_reachable"])
                if isinstance(internet_summary.get("internet_reachable"), bool)
                else None
            ),
            internet_check_error=str(internet_summary["internet_check_error"])
            if internet_summary.get("internet_check_error")
            else None,
        )
        self._record_host_resource_sample(summary, stats=stats)
        return summary

    def _record_host_resource_sample(self, summary: HostResourceSummary, *, stats: SystemStats) -> None:
        try:
            metrics = summary.model_dump(exclude_none=True)
            metrics.update(
                {
                    "swap_total_bytes": stats.swap.total,
                    "swap_used_bytes": stats.swap.used,
                    "swap_free_bytes": stats.swap.free,
                    "swap_percent": stats.swap.percent,
                }
            )
            self._resource_history_store.insert_sample(
                scope="host",
                resource_id="host",
                sampled_at=self._now_iso(),
                metrics=metrics,
                metadata={
                    "resource_observer": "supervisor",
                    "supervisor_id": self._supervisor_id(),
                    "host_id": self._host_identity().host_id,
                    "hostname": self._host_identity().hostname,
                },
            )
        except Exception:
            return

    def _managed_nodes(self) -> list[ManagedNodeSummary]:
        runtimes = self._runtime_service.list_standalone_addon_runtimes()
        return [
            ManagedNodeSummary(
                node_id=item.addon_id,
                lifecycle_state=item.lifecycle_state,
                desired_state=item.desired_state,
                runtime_state=item.runtime_state,
                health_status=item.health_status,
                active_version=item.active_version,
                running=item.running,
                last_action=item.last_action,
                last_action_at=item.last_action_at,
            )
            for item in runtimes
        ]

    def _runtime_stale_after_s(self) -> int:
        raw = str(getenv("HEXE_SUPERVISOR_NODE_HEARTBEAT_STALE_S", "60")).strip()
        try:
            parsed = int(raw)
        except Exception:
            return 60
        return max(1, parsed)

    def _runtime_offline_after_s(self) -> int:
        raw = str(getenv("HEXE_SUPERVISOR_NODE_HEARTBEAT_OFFLINE_S", "180")).strip()
        try:
            parsed = int(raw)
        except Exception:
            return 180
        return max(self._runtime_stale_after_s() + 1, parsed)

    def _resolve_node_api_base_url(self, node_id: str) -> str:
        runtime = self._runtime_nodes_store.get(node_id)
        base_url = str(runtime.api_base_url or "").strip() if runtime is not None else ""
        if not base_url and self._node_registrations_store is not None:
            record = self._node_registrations_store.get(node_id)
            if record is not None:
                base_url = str(record.api_base_url or "").strip()
        if not base_url:
            raise HTTPException(status_code=412, detail="node_api_base_url_missing")
        if not base_url.startswith("http"):
            raise HTTPException(status_code=400, detail="node_api_base_url_invalid")
        return base_url.rstrip("/")

    def _node_api_request(
        self,
        node_id: str,
        *,
        method: str,
        path: str,
        payload: dict | None = None,
        timeout_s: float = 4.0,
    ) -> dict:
        base_url = self._resolve_node_api_base_url(node_id)
        url = f"{base_url}{path}"
        try:
            with httpx.Client(timeout=timeout_s) as client:
                response = client.request(method.upper(), url, json=payload)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"node_api_unreachable: {exc}") from exc
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise HTTPException(status_code=502, detail=f"node_api_error: {response.status_code} {detail}")
        try:
            return response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="node_api_invalid_json") from exc

    def _normalize_node_services(self, payload: dict) -> list[SupervisorNodeServiceSummary]:
        services_raw = payload.get("services")
        if not isinstance(services_raw, dict):
            services_raw = payload
        normalized: list[SupervisorNodeServiceSummary] = []
        for service_id, value in services_raw.items():
            if isinstance(value, dict):
                _, observed = self._observed_resource_view({}, value)
                state = str(observed.get("state") or observed.get("status") or observed.get("service_state") or "unknown")
                normalized.append(
                    SupervisorNodeServiceSummary(
                        service_id=str(service_id),
                        service_name=str(observed.get("service_name") or observed.get("name") or service_id),
                        service_state=state,
                        desired_state=str(observed.get("desired_state") or "") or None,
                        health_status=str(observed.get("health_status") or "") or None,
                        updated_at=str(observed.get("updated_at") or "") or None,
                        pid=observed.get("pid") if isinstance(observed.get("pid"), int) else None,
                        container_name=str(observed.get("container_name") or "") or None,
                        container_id=str(observed.get("container_id") or "") or None,
                        cpu_percent=observed.get("cpu_percent") if isinstance(observed.get("cpu_percent"), int | float) else None,
                        mem_percent=observed.get("mem_percent") if isinstance(observed.get("mem_percent"), int | float) else None,
                        rss_bytes=observed.get("rss_bytes") if isinstance(observed.get("rss_bytes"), int) else None,
                        resource_source=str(observed.get("resource_source") or "") or None,
                        sampled_at=str(observed.get("sampled_at") or "") or None,
                        metadata={k: v for k, v in observed.items() if k not in {"state", "status", "service_state"}},
                    )
                )
            else:
                normalized.append(
                    SupervisorNodeServiceSummary(
                        service_id=str(service_id),
                        service_name=str(service_id),
                        service_state=str(value or "unknown"),
                    )
                )
        return normalized

    def node_services_status(self, node_id: str) -> SupervisorNodeServicesSummary:
        payload = self._node_api_request(node_id, method="GET", path="/api/services/status")
        return SupervisorNodeServicesSummary(
            node_id=node_id,
            api_base_url=self._resolve_node_api_base_url(node_id),
            services=self._normalize_node_services(payload),
        )

    def node_service_action(self, node_id: str, *, service_id: str, action: str) -> SupervisorNodeServiceActionResult:
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"start", "stop", "restart"}:
            raise HTTPException(status_code=400, detail="unsupported_service_action")
        self._append_boot_log(
            "service_action",
            context={"runtime_id": node_id, "service_id": service_id, "action": normalized_action},
        )
        payload = {"target": service_id}
        response = self._node_api_request(
            node_id,
            method="POST",
            path=f"/api/services/{normalized_action}",
            payload=payload,
            timeout_s=self._node_service_action_timeout_s(),
        )
        return SupervisorNodeServiceActionResult(
            action=normalized_action,
            node_id=node_id,
            service_id=str(service_id),
            result=response if isinstance(response, dict) else {"response": response},
        )

    def _node_service_action_timeout_s(self) -> float:
        raw = str(getenv("HEXE_SUPERVISOR_NODE_SERVICE_ACTION_TIMEOUT_S", "30")).strip()
        try:
            parsed = float(raw)
        except Exception:
            return 30.0
        return max(4.0, parsed)

    def _freshness_state(self, last_seen_at: str | None, *, health_status: str, runtime_state: str) -> str:
        if str(runtime_state or "").strip().lower() == "error" or str(health_status or "").strip().lower() == "error":
            return "error"
        if not last_seen_at:
            return "offline"
        try:
            seen = datetime.fromisoformat(str(last_seen_at).replace("Z", "+00:00"))
        except Exception:
            return "offline"
        age_s = max(0.0, (datetime.now(timezone.utc) - seen).total_seconds())
        if age_s >= self._runtime_offline_after_s():
            return "offline"
        if age_s >= self._runtime_stale_after_s():
            return "stale"
        return "online"

    def _observed_resource_view(
        self,
        resource_usage: dict[str, object] | None,
        runtime_metadata: dict[str, object] | None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        try:
            return self._resource_monitor.enrich(resource_usage, runtime_metadata)
        except Exception as exc:
            usage = dict(resource_usage or {})
            metadata = dict(runtime_metadata or {})
            metadata["resource_observer"] = "supervisor"
            metadata["resource_observer_error"] = str(exc) or type(exc).__name__
            return usage, metadata

    def _resource_metric_view(self, entry: dict[str, object] | None) -> dict[str, object]:
        if not isinstance(entry, dict):
            return {}
        keys = {
            "pid",
            "running",
            "cpu_percent",
            "mem_percent",
            "rss_bytes",
            "rps",
            "latency_ms_avg",
            "latency_ms_p95",
            "error_rate",
            "inflight",
            "process_status",
            "container_name",
            "container_id",
            "resource_source",
            "sampled_at",
            "last_error",
        }
        return {key: value for key, value in entry.items() if key in keys and value is not None}

    def _nested_resource_entries(self, runtime_metadata: dict[str, object] | None) -> list[tuple[str, str, dict[str, object]]]:
        entries: list[tuple[str, str, dict[str, object]]] = []
        if not isinstance(runtime_metadata, dict):
            return entries
        services = runtime_metadata.get("services")
        if isinstance(services, list):
            for item in services:
                if not isinstance(item, dict):
                    continue
                service_id = str(item.get("service_id") or item.get("name") or item.get("service_name") or "").strip()
                metrics = self._resource_metric_view(item)
                if service_id and metrics:
                    entries.append(("service", service_id, metrics))
        elif isinstance(services, dict):
            for key, item in services.items():
                if not isinstance(item, dict):
                    continue
                service_id = str(item.get("service_id") or item.get("name") or item.get("service_name") or key or "").strip()
                metrics = self._resource_metric_view(item)
                if service_id and metrics:
                    entries.append(("service", service_id, metrics))
        containers = runtime_metadata.get("containers")
        if isinstance(containers, list):
            for item in containers:
                if not isinstance(item, dict):
                    continue
                container_id = str(item.get("container_name") or item.get("container_id") or item.get("name") or "").strip()
                metrics = self._resource_metric_view(item)
                if container_id and metrics:
                    entries.append(("container", container_id, metrics))
        return entries

    def _record_runtime_resource_sample(
        self,
        *,
        scope: str,
        resource_id: str,
        resource_usage: dict[str, object],
        runtime_metadata: dict[str, object],
        metadata: dict[str, object],
    ) -> None:
        try:
            metrics = self._resource_metric_view(resource_usage)
            if metrics:
                self._resource_history_store.insert_sample(
                    scope=scope,
                    resource_id=resource_id,
                    sampled_at=metrics.get("sampled_at") or self._now_iso(),
                    metrics=metrics,
                    metadata={**metadata, "resource_observer": "supervisor"},
                )
                self._record_resource_health_markers(
                    scope=scope,
                    resource_id=resource_id,
                    metrics=metrics,
                    metadata=metadata,
                )
            for entry_kind, entry_id, entry_metrics in self._nested_resource_entries(runtime_metadata):
                child_scope = f"{scope}_{entry_kind}"
                child_resource_id = f"{resource_id}/{entry_id}"
                self._resource_history_store.insert_sample(
                    scope=child_scope,
                    resource_id=child_resource_id,
                    sampled_at=entry_metrics.get("sampled_at") or self._now_iso(),
                    metrics=entry_metrics,
                    metadata={
                        **metadata,
                        "resource_observer": "supervisor",
                        "parent_scope": scope,
                        "parent_resource_id": resource_id,
                        "entry_kind": entry_kind,
                        "entry_id": entry_id,
                    },
                )
                self._record_resource_health_markers(
                    scope=child_scope,
                    resource_id=child_resource_id,
                    metrics=entry_metrics,
                    metadata={**metadata, "parent_scope": scope, "parent_resource_id": resource_id},
                )
        except Exception:
            return

    def _record_resource_health_markers(
        self,
        *,
        scope: str,
        resource_id: str,
        metrics: dict[str, object],
        metadata: dict[str, object],
    ) -> None:
        if metrics.get("running") is False or str(metrics.get("last_error") or "") == "process_unavailable":
            self._record_runtime_lifecycle_marker(
                scope=scope,
                resource_id=resource_id,
                event_type="process_unavailable",
                message=f"{resource_id} process unavailable",
                payload={"metrics": metrics, **metadata},
            )
        last_error = str(metrics.get("last_error") or "").strip()
        if last_error and last_error != "process_unavailable":
            event_type = "runtime_resource_error"
            lowered = last_error.lower()
            if "oom" in lowered:
                event_type = "oom_indicator"
            elif "segv" in lowered or "sigsegv" in lowered:
                event_type = "segfault_indicator"
            self._record_runtime_lifecycle_marker(
                scope=scope,
                resource_id=resource_id,
                event_type=event_type,
                message=f"{resource_id} resource error: {last_error}",
                payload={"last_error": last_error, "metrics": metrics, **metadata},
            )

    def _record_runtime_lifecycle_marker(
        self,
        *,
        scope: str,
        resource_id: str,
        event_type: str,
        message: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        try:
            self._resource_history_store.record_event(
                scope=scope,
                resource_id=resource_id,
                event_type=event_type,
                message=message,
                payload={**dict(payload or {}), "resource_observer": "supervisor"},
            )
        except Exception:
            return

    def _core_runtime_heartbeat_interval_s(self) -> float:
        raw = str(getenv("HEXE_SUPERVISOR_CORE_HEARTBEAT_S", "5")).strip()
        try:
            parsed = float(raw)
        except Exception:
            return 5.0
        return max(1.0, parsed)

    def _core_runtime_stale_after_s(self) -> float:
        raw = str(getenv("HEXE_SUPERVISOR_CORE_HEARTBEAT_STALE_S", "")).strip()
        if raw:
            try:
                parsed = float(raw)
                return max(1.0, parsed)
            except Exception:
                pass
        return max(1.0, self._core_runtime_heartbeat_interval_s() * 2)

    def _core_runtime_offline_after_s(self) -> float:
        raw = str(getenv("HEXE_SUPERVISOR_CORE_HEARTBEAT_OFFLINE_S", "")).strip()
        if raw:
            try:
                parsed = float(raw)
                return max(self._core_runtime_stale_after_s() + 1.0, parsed)
            except Exception:
                pass
        return max(self._core_runtime_stale_after_s() + 1.0, self._core_runtime_heartbeat_interval_s() * 5)

    def _core_freshness_state(self, last_seen_at: str | None, *, health_status: str, runtime_state: str) -> str:
        if str(runtime_state or "").strip().lower() == "error" or str(health_status or "").strip().lower() == "error":
            return "error"
        if not last_seen_at:
            return "offline"
        try:
            seen = datetime.fromisoformat(str(last_seen_at).replace("Z", "+00:00"))
        except Exception:
            return "offline"
        age_s = max(0.0, (datetime.now(timezone.utc) - seen).total_seconds())
        if age_s >= self._core_runtime_offline_after_s():
            return "offline"
        if age_s >= self._core_runtime_stale_after_s():
            return "stale"
        return "online"

    def _registered_runtime_summary(self, record: SupervisorRuntimeNodeRecord) -> SupervisorRegisteredRuntimeSummary:
        merged = merge_runtime_identity(record, self._node_registrations_store)
        resource_usage, runtime_metadata = self._observed_resource_view(merged.resource_usage, merged.runtime_metadata)
        self._record_runtime_resource_sample(
            scope="runtime",
            resource_id=merged.node_id,
            resource_usage=resource_usage,
            runtime_metadata=runtime_metadata,
            metadata={
                "node_id": merged.node_id,
                "node_name": merged.node_name,
                "node_type": merged.node_type,
                "runtime_kind": "real_node",
                "runtime_state": merged.runtime_state,
                "lifecycle_state": merged.lifecycle_state,
                "health_status": merged.health_status,
            },
        )
        return SupervisorRegisteredRuntimeSummary(
            node_id=merged.node_id,
            node_name=merged.node_name,
            node_type=merged.node_type,
            desired_state=merged.desired_state,
            runtime_state=merged.runtime_state,
            lifecycle_state=merged.lifecycle_state,
            health_status=merged.health_status,
            freshness_state=self._freshness_state(
                merged.last_seen_at,
                health_status=merged.health_status,
                runtime_state=merged.runtime_state,
            ),
            host_id=merged.host_id,
            hostname=merged.hostname,
            api_base_url=merged.api_base_url,
            ui_base_url=merged.ui_base_url,
            health_detail=merged.health_detail,
            registered_at=merged.registered_at,
            updated_at=merged.updated_at,
            last_seen_at=merged.last_seen_at,
            last_action=merged.last_action,
            last_action_at=merged.last_action_at,
            last_error=merged.last_error,
            running=merged.running,
            resource_usage=resource_usage,
            runtime_metadata=runtime_metadata,
        )

    def list_registered_runtimes(self) -> list[SupervisorRegisteredRuntimeSummary]:
        return [self._registered_runtime_summary(item) for item in self._runtime_nodes_store.list()]

    def get_registered_runtime(self, node_id: str) -> SupervisorRegisteredRuntimeSummary:
        record = self._runtime_nodes_store.get(node_id)
        if record is None:
            raise HTTPException(status_code=404, detail="runtime_not_registered")
        return self._registered_runtime_summary(record)

    def register_runtime(self, payload: SupervisorRuntimeRegistrationRequest) -> SupervisorRegisteredRuntimeSummary:
        record = self._runtime_nodes_store.upsert_registration(payload=payload.model_dump())
        return self._registered_runtime_summary(record)

    def heartbeat_runtime(self, payload: SupervisorRuntimeHeartbeatRequest) -> SupervisorRegisteredRuntimeSummary:
        record = self._runtime_nodes_store.apply_heartbeat(payload.node_id, payload=payload.model_dump())
        if record is None:
            raise HTTPException(status_code=404, detail="runtime_not_registered")
        return self._registered_runtime_summary(record)

    def _registered_runtime_action(
        self,
        node_id: str,
        *,
        action: str,
        desired_state: str,
        lifecycle_state: str,
    ) -> SupervisorRuntimeActionResult:
        self._append_boot_log(
            "runtime_action",
            context={
                "runtime_id": node_id,
                "action": action,
                "scope": "registered_runtime",
                "message": f"{action.capitalize()} {node_id}",
            },
        )
        self._record_runtime_lifecycle_marker(
            scope="runtime",
            resource_id=node_id,
            event_type=f"{action}_requested",
            message=f"{action.capitalize()} requested for {node_id}",
            payload={"runtime_id": node_id, "action": action, "desired_state": desired_state, "lifecycle_state": lifecycle_state},
        )
        record = self._runtime_nodes_store.apply_action(
            node_id,
            action=action,
            desired_state=desired_state,
            lifecycle_state=lifecycle_state,
        )
        if record is None:
            raise HTTPException(status_code=404, detail="runtime_not_registered")
        return SupervisorRuntimeActionResult(action=action, runtime=self._registered_runtime_summary(record))

    def start_registered_runtime(self, node_id: str) -> SupervisorRuntimeActionResult:
        return self._registered_runtime_action(
            node_id,
            action="start",
            desired_state="running",
            lifecycle_state="starting",
        )

    def stop_registered_runtime(self, node_id: str) -> SupervisorRuntimeActionResult:
        return self._registered_runtime_action(
            node_id,
            action="stop",
            desired_state="stopped",
            lifecycle_state="stopping",
        )

    def restart_registered_runtime(self, node_id: str) -> SupervisorRuntimeActionResult:
        return self._registered_runtime_action(
            node_id,
            action="restart",
            desired_state="running",
            lifecycle_state="restarting",
        )

    def _normalize_core_runtime_kind(self, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"core", "core_service"}:
            return "core_service"
        if normalized in {"addon", "aux_service", "aux_container"}:
            return normalized
        return normalized or "core_service"

    def _normalize_core_management_mode(self, value: str, *, runtime_kind: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"monitor", "manage"}:
            normalized = "monitor" if runtime_kind == "core_service" else "manage"
        if runtime_kind == "core_service":
            return "monitor"
        return normalized

    def _core_runtime_summary(self, record: SupervisorCoreRuntimeRecord) -> SupervisorCoreRuntimeSummary:
        resource_usage, runtime_metadata = self._observed_resource_view(record.resource_usage, record.runtime_metadata)
        self._record_runtime_resource_sample(
            scope="core_runtime",
            resource_id=record.runtime_id,
            resource_usage=resource_usage,
            runtime_metadata=runtime_metadata,
            metadata={
                "runtime_id": record.runtime_id,
                "runtime_name": record.runtime_name,
                "runtime_kind": record.runtime_kind,
                "management_mode": record.management_mode,
                "runtime_state": record.runtime_state,
                "lifecycle_state": record.lifecycle_state,
                "health_status": record.health_status,
            },
        )
        return SupervisorCoreRuntimeSummary(
            runtime_id=record.runtime_id,
            runtime_name=record.runtime_name,
            runtime_kind=record.runtime_kind,
            management_mode=record.management_mode,
            desired_state=record.desired_state,
            runtime_state=record.runtime_state,
            lifecycle_state=record.lifecycle_state,
            health_status=record.health_status,
            freshness_state=self._core_freshness_state(
                record.last_seen_at,
                health_status=record.health_status,
                runtime_state=record.runtime_state,
            ),
            host_id=record.host_id,
            hostname=record.hostname,
            registered_at=record.registered_at,
            updated_at=record.updated_at,
            last_seen_at=record.last_seen_at,
            last_action=record.last_action,
            last_action_at=record.last_action_at,
            last_error=record.last_error,
            running=record.running,
            resource_usage=resource_usage,
            runtime_metadata=runtime_metadata,
        )

    def list_core_runtimes(self) -> list[SupervisorCoreRuntimeSummary]:
        return [self._core_runtime_summary(item) for item in self._core_runtime_store.list()]

    def get_core_runtime(self, runtime_id: str) -> SupervisorCoreRuntimeSummary:
        record = self._core_runtime_store.get(runtime_id)
        if record is None:
            raise HTTPException(status_code=404, detail="core_runtime_not_registered")
        return self._core_runtime_summary(record)

    def register_core_runtime(self, payload: SupervisorCoreRuntimeRegistrationRequest) -> SupervisorCoreRuntimeSummary:
        data = payload.model_dump()
        runtime_kind = self._normalize_core_runtime_kind(data.get("runtime_kind"))
        data["runtime_kind"] = runtime_kind
        data["management_mode"] = self._normalize_core_management_mode(data.get("management_mode"), runtime_kind=runtime_kind)
        record = self._core_runtime_store.upsert_registration(payload=data)
        return self._core_runtime_summary(record)

    def heartbeat_core_runtime(self, payload: SupervisorCoreRuntimeHeartbeatRequest) -> SupervisorCoreRuntimeSummary:
        record = self._core_runtime_store.apply_heartbeat(payload.runtime_id, payload=payload.model_dump())
        if record is None:
            raise HTTPException(status_code=404, detail="core_runtime_not_registered")
        return self._core_runtime_summary(record)

    def _core_runtime_action(
        self,
        runtime_id: str,
        *,
        action: str,
        desired_state: str,
        lifecycle_state: str,
    ) -> SupervisorCoreRuntimeActionResult:
        record = self._core_runtime_store.get(runtime_id)
        if record is None:
            raise HTTPException(status_code=404, detail="core_runtime_not_registered")
        if str(record.management_mode or "").strip().lower() != "manage":
            raise HTTPException(status_code=409, detail="core_runtime_monitor_only")
        self._record_runtime_lifecycle_marker(
            scope="core_runtime",
            resource_id=runtime_id,
            event_type=f"{action}_requested",
            message=f"{action.capitalize()} requested for {runtime_id}",
            payload={"runtime_id": runtime_id, "action": action, "desired_state": desired_state, "lifecycle_state": lifecycle_state},
        )
        self._append_boot_log(
            "runtime_action",
            context={
                "runtime_id": runtime_id,
                "action": action,
                "scope": "core_runtime",
                "message": f"{action.capitalize()} {runtime_id}",
            },
        )
        units = self._extract_systemd_units(record.runtime_metadata)
        if units:
            ok, error = self._systemctl_action(units, action)
            if not ok:
                self._append_boot_log(
                    "runtime_action",
                    context={
                        "runtime_id": runtime_id,
                        "action": action,
                        "scope": "core_runtime",
                        "status": "systemd_failed",
                        "error": error,
                    },
                )
                raise HTTPException(status_code=502, detail="systemd_action_failed")
        updated = self._core_runtime_store.apply_action(
            runtime_id,
            action=action,
            desired_state=desired_state,
            lifecycle_state=lifecycle_state,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="core_runtime_not_registered")
        return SupervisorCoreRuntimeActionResult(action=action, runtime=self._core_runtime_summary(updated))

    def start_core_runtime(self, runtime_id: str) -> SupervisorCoreRuntimeActionResult:
        return self._core_runtime_action(
            runtime_id,
            action="start",
            desired_state="running",
            lifecycle_state="starting",
        )

    def stop_core_runtime(self, runtime_id: str) -> SupervisorCoreRuntimeActionResult:
        return self._core_runtime_action(
            runtime_id,
            action="stop",
            desired_state="stopped",
            lifecycle_state="stopping",
        )

    def restart_core_runtime(self, runtime_id: str) -> SupervisorCoreRuntimeActionResult:
        return self._core_runtime_action(
            runtime_id,
            action="restart",
            desired_state="running",
            lifecycle_state="restarting",
        )

    def system_stats(self, *, api_metrics=None) -> SystemStats:
        return collect_system_stats(api_metrics=api_metrics)

    def system_snapshot(
        self,
        *,
        api_metrics=None,
        api_snapshot: dict[str, Any] | None = None,
        registry=None,
        quiet_thresholds=None,
    ) -> SystemStatsSnapshot:
        return collect_system_snapshot(
            api_metrics=api_metrics,
            api_snapshot=api_snapshot,
            registry=registry,
            quiet_thresholds=quiet_thresholds,
        )

    def process_stats(self) -> dict[str, Any]:
        return collect_process_stats()

    def process_summary(self) -> ProcessResourceSummary:
        stats = self.process_stats()
        return ProcessResourceSummary(
            rss_bytes=stats.get("rss_bytes"),
            cpu_percent=stats.get("cpu_percent"),
            open_fds=stats.get("open_fds"),
            threads=stats.get("threads"),
        )

    def resources_summary(self) -> HostResourceSummary:
        return self._host_resources()

    def resource_history(self, *, range_value: str = "24h", step_value: str | None = "60s") -> dict[str, Any]:
        return {
            "scope": "host",
            "resource_id": "host",
            "range": range_value,
            "step": step_value,
            "samples": self._resource_history_store.samples(
                scope="host",
                resource_id="host",
                range_value=range_value,
                step_value=step_value,
            ),
            "events": self._resource_history_store.events(
                scope="host",
                resource_id="host",
                range_value=range_value,
            ),
        }

    def resource_history_status(self) -> dict[str, Any]:
        return self._resource_history_store.status()

    def maintain_resource_history(self, *, action: str = "compact") -> dict[str, Any]:
        try:
            return self._resource_history_store.maintain(action=action)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def runtime_resource_history(self, node_id: str, *, range_value: str = "24h", step_value: str | None = "60s") -> dict[str, Any]:
        clean_node_id = str(node_id or "").strip()
        if not clean_node_id:
            raise HTTPException(status_code=400, detail="runtime_id_required")
        if self._runtime_nodes_store.get(clean_node_id) is None:
            raise HTTPException(status_code=404, detail="runtime_not_registered")
        child_prefix = f"{clean_node_id}/"
        return {
            "scope": "runtime",
            "resource_id": clean_node_id,
            "range": range_value,
            "step": step_value,
            "samples": self._resource_history_store.samples(
                scope="runtime",
                resource_id=clean_node_id,
                range_value=range_value,
                step_value=step_value,
            ),
            "events": self._resource_history_store.events(
                scope="runtime",
                resource_id=clean_node_id,
                range_value=range_value,
            ),
            "service_samples": self._resource_history_store.samples_with_resource_prefix(
                scope="runtime_service",
                resource_id_prefix=child_prefix,
                range_value=range_value,
                step_value=step_value,
            ),
            "container_samples": self._resource_history_store.samples_with_resource_prefix(
                scope="runtime_container",
                resource_id_prefix=child_prefix,
                range_value=range_value,
                step_value=step_value,
            ),
        }

    def core_runtime_resource_history(
        self,
        runtime_id: str,
        *,
        range_value: str = "24h",
        step_value: str | None = "60s",
    ) -> dict[str, Any]:
        clean_runtime_id = str(runtime_id or "").strip()
        if not clean_runtime_id:
            raise HTTPException(status_code=400, detail="runtime_id_required")
        if self._core_runtime_store.get(clean_runtime_id) is None:
            raise HTTPException(status_code=404, detail="core_runtime_not_registered")
        child_prefix = f"{clean_runtime_id}/"
        return {
            "scope": "core_runtime",
            "resource_id": clean_runtime_id,
            "range": range_value,
            "step": step_value,
            "samples": self._resource_history_store.samples(
                scope="core_runtime",
                resource_id=clean_runtime_id,
                range_value=range_value,
                step_value=step_value,
            ),
            "events": self._resource_history_store.events(
                scope="core_runtime",
                resource_id=clean_runtime_id,
                range_value=range_value,
            ),
            "service_samples": self._resource_history_store.samples_with_resource_prefix(
                scope="core_runtime_service",
                resource_id_prefix=child_prefix,
                range_value=range_value,
                step_value=step_value,
            ),
            "container_samples": self._resource_history_store.samples_with_resource_prefix(
                scope="core_runtime_container",
                resource_id_prefix=child_prefix,
                range_value=range_value,
                step_value=step_value,
            ),
        }

    def runtime_summary(self) -> SupervisorRuntimeSummary:
        managed_nodes = self._managed_nodes()
        return SupervisorRuntimeSummary(
            host=self._host_identity(),
            resources=self._host_resources(),
            process=self.process_summary(),
            managed_node_count=len(managed_nodes),
            managed_nodes=managed_nodes,
        )

    def boot_loop_status(self) -> dict[str, Any]:
        return dict(self._boot_loop_status)

    def _boot_step_timeout_s(self) -> float:
        raw = str(getenv("HEXE_SUPERVISOR_BOOT_STEP_TIMEOUT_S", "60")).strip()
        try:
            parsed = float(raw)
        except Exception:
            return 60.0
        return max(5.0, parsed)

    def _boot_poll_s(self) -> float:
        raw = str(getenv("HEXE_SUPERVISOR_BOOT_POLL_S", "2")).strip()
        try:
            parsed = float(raw)
        except Exception:
            return 2.0
        return max(0.5, parsed)

    def _systemctl_action(self, units: list[str], action: str) -> tuple[bool, str | None]:
        if not units:
            return False, "systemd_units_missing"
        if shutil.which("systemctl") is None:
            return False, "systemctl_not_found"
        try:
            result = subprocess.run(
                ["systemctl", "--user", action, *units],
                capture_output=True,
                text=True,
                timeout=8.0,
                check=False,
            )
        except Exception as exc:
            return False, str(exc)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return False, detail or f"systemctl_exit_{result.returncode}"
        return True, None

    def _extract_systemd_units(self, runtime_metadata: dict[str, Any] | None) -> list[str]:
        if not runtime_metadata:
            return []
        unit = runtime_metadata.get("systemd_unit") or runtime_metadata.get("systemd_service")
        if isinstance(unit, str) and unit.strip():
            return [unit.strip()]
        units = runtime_metadata.get("systemd_units")
        if isinstance(units, list):
            return [str(item).strip() for item in units if isinstance(item, str) and item.strip()]
        return []

    def _core_runtime_ready(self, record: SupervisorCoreRuntimeRecord) -> bool:
        freshness = self._core_freshness_state(
            record.last_seen_at,
            health_status=record.health_status,
            runtime_state=record.runtime_state,
        )
        if freshness != "online":
            return False
        if str(record.health_status or "").strip().lower() in {"error", "unhealthy"}:
            return False
        return str(record.runtime_state or "").strip().lower() == "running"

    def _node_runtime_ready(self, record: SupervisorRuntimeNodeRecord) -> bool:
        freshness = self._freshness_state(
            record.last_seen_at,
            health_status=record.health_status,
            runtime_state=record.runtime_state,
        )
        if freshness != "online":
            return False
        if str(record.health_status or "").strip().lower() in {"error", "unhealthy"}:
            return False
        return str(record.runtime_state or "").strip().lower() == "running"

    def _wait_for_core_runtime(self, runtime_id: str, timeout_s: float) -> bool:
        start = time.monotonic()
        while time.monotonic() - start < timeout_s:
            record = self._core_runtime_store.get(runtime_id)
            if record and self._core_runtime_ready(record):
                return True
            time.sleep(self._boot_poll_s())
        return False

    def _wait_for_node_runtime(self, node_id: str, timeout_s: float) -> bool:
        start = time.monotonic()
        while time.monotonic() - start < timeout_s:
            record = self._runtime_nodes_store.get(node_id)
            if record and self._node_runtime_ready(record):
                return True
            time.sleep(self._boot_poll_s())
        return False

    def _dependency_ready(self, dependency: str) -> bool:
        dep = str(dependency or "").strip()
        if not dep:
            return True
        if dep.startswith("node_type:"):
            node_type = dep.split(":", 1)[1].strip()
            return any(
                self._node_runtime_ready(record)
                for record in self._runtime_nodes_store.list()
                if record.node_type == node_type
            )
        record = self._core_runtime_store.get(dep)
        if record is None:
            record = self._core_runtime_store.get(f"addon:{dep}")
        if record is not None:
            return self._core_runtime_ready(record)
        return any(
            self._node_runtime_ready(record)
            for record in self._runtime_nodes_store.list()
            if record.node_type == dep
        )

    def _wait_for_dependencies(self, dependencies: list[str], timeout_s: float) -> bool:
        if not dependencies:
            return True
        start = time.monotonic()
        while time.monotonic() - start < timeout_s:
            if all(self._dependency_ready(dep) for dep in dependencies):
                return True
            time.sleep(self._boot_poll_s())
        return False

    def run_boot_loop(self) -> dict[str, Any]:
        plan, warnings = load_boot_order_plan()
        results: dict[str, Any] = {
            "warnings": warnings,
            "core": [],
            "nodes": [],
        }
        started_at = self._now_iso()
        self._boot_loop_status = {
            "state": "running",
            "started_at": started_at,
            "updated_at": started_at,
            "warnings": list(warnings),
            "results": {},
        }
        self._append_boot_log("boot_loop_start", context={"started_at": started_at})
        timeout_s = self._boot_step_timeout_s()
        core_order = plan.get("core", {}).get("boot_order", {})
        core_deps = plan.get("core", {}).get("dependencies", {})
        for runtime_id, _ in sorted(core_order.items(), key=lambda item: (item[1], item[0])):
            deps = core_deps.get(runtime_id, [])
            if not self._wait_for_dependencies(deps, timeout_s):
                entry = {"runtime_id": runtime_id, "status": "dependency_timeout"}
                results["core"].append(entry)
                self._append_boot_log("boot_loop_step", context={**entry, "message": f"{runtime_id} dependency timeout"})
                continue
            record = self._core_runtime_store.get(runtime_id)
            if record is None:
                entry = {"runtime_id": runtime_id, "status": "missing"}
                results["core"].append(entry)
                self._append_boot_log("boot_loop_step", context={**entry, "message": f"{runtime_id} missing"})
                continue
            self._append_boot_log(
                "boot_loop_step",
                context={"runtime_id": runtime_id, "status": "starting", "message": f"Starting {runtime_id}"},
            )
            if str(record.management_mode or "").strip().lower() == "manage":
                units = self._extract_systemd_units(record.runtime_metadata)
                if units:
                    ok, error = self._systemctl_action(units, "start")
                    if not ok:
                        entry = {"runtime_id": runtime_id, "status": "start_failed", "error": error}
                        results["core"].append(entry)
                        self._append_boot_log(
                            "boot_loop_step",
                            context={**entry, "message": f"{runtime_id} start failed"},
                        )
                        continue
                self.start_core_runtime(runtime_id)
            ready = self._wait_for_core_runtime(runtime_id, timeout_s)
            entry = {"runtime_id": runtime_id, "status": "ready" if ready else "timeout"}
            results["core"].append(entry)
            if ready:
                self._append_boot_log(
                    "boot_loop_step",
                    context={**entry, "message": f"{runtime_id} healthy"},
                )
            else:
                self._append_boot_log(
                    "boot_loop_step",
                    context={**entry, "message": f"{runtime_id} health timeout"},
                )

        node_order = plan.get("nodes", {}).get("boot_order", {})
        node_deps = plan.get("nodes", {}).get("dependencies", {})
        for node_type, _ in sorted(node_order.items(), key=lambda item: (item[1], item[0])):
            deps = node_deps.get(node_type, [])
            if not self._wait_for_dependencies(deps, timeout_s):
                entry = {"node_type": node_type, "status": "dependency_timeout"}
                results["nodes"].append(entry)
                self._append_boot_log("boot_loop_step", context={**entry, "message": f"{node_type} dependency timeout"})
                continue
            runtimes = [item for item in self._runtime_nodes_store.list() if item.node_type == node_type]
            if not runtimes:
                entry = {"node_type": node_type, "status": "missing"}
                results["nodes"].append(entry)
                self._append_boot_log("boot_loop_step", context={**entry, "message": f"{node_type} missing"})
                continue
            for record in sorted(runtimes, key=lambda item: (item.node_name, item.node_id)):
                self._append_boot_log(
                    "boot_loop_step",
                    context={"node_type": node_type, "node_id": record.node_id, "status": "starting", "message": f"Starting {record.node_id}"},
                )
                self.start_registered_runtime(record.node_id)
                ready = self._wait_for_node_runtime(record.node_id, timeout_s)
                entry = {
                    "node_type": node_type,
                    "node_id": record.node_id,
                    "status": "ready" if ready else "timeout",
                }
                results["nodes"].append(entry)
                if ready:
                    self._append_boot_log(
                        "boot_loop_step",
                        context={**entry, "message": f"{record.node_id} healthy"},
                    )
                else:
                    self._append_boot_log(
                        "boot_loop_step",
                        context={**entry, "message": f"{record.node_id} health timeout"},
                    )
        finished_at = self._now_iso()
        self._boot_loop_status = {
            "state": "finished",
            "started_at": started_at,
            "finished_at": finished_at,
            "updated_at": finished_at,
            "warnings": list(warnings),
            "results": results,
        }
        self._append_boot_log("boot_loop_complete", context={"finished_at": finished_at})
        return results

    def list_managed_nodes(self) -> list[ManagedNodeSummary]:
        return self._managed_nodes()

    def admission_summary(
        self,
        *,
        total_capacity_units: int = 100,
        reserve_units: int = 5,
        headroom_pct: float = 0.05,
    ) -> SupervisorAdmissionContextSummary:
        resources = self._host_resources()
        managed_nodes = self._managed_nodes()
        healthy_count = sum(1 for item in managed_nodes if str(item.health_status or "").strip().lower() == "healthy")

        busy = 0
        if resources.cpu_percent_total >= 95 or resources.memory_percent >= 95:
            busy = 10
        elif resources.cpu_percent_total >= 85 or resources.memory_percent >= 85:
            busy = 8
        elif resources.cpu_percent_total >= 70 or resources.memory_percent >= 70:
            busy = 6
        elif resources.cpu_percent_total >= 50 or resources.memory_percent >= 50:
            busy = 3

        busy_to_percent = {
            0: 1.00,
            1: 1.00,
            2: 1.00,
            3: 0.80,
            4: 0.65,
            5: 0.50,
            6: 0.35,
            7: 0.25,
            8: 0.15,
            9: 0.10,
            10: 0.00,
        }
        usable = int((total_capacity_units * busy_to_percent[busy]) * max(0.0, 1.0 - headroom_pct)) - reserve_units
        available_capacity = max(0, usable)
        host_ready = available_capacity > 0 and resources.memory_available_bytes > 0

        return SupervisorAdmissionContextSummary(
            admission_state="ready" if host_ready else "degraded",
            execution_host_ready=host_ready,
            unavailable_reason=None if host_ready else "host_capacity_unavailable",
            host_busy_rating=busy,
            total_capacity_units=max(0, int(total_capacity_units)),
            available_capacity_units=available_capacity,
            managed_node_count=len(managed_nodes),
            healthy_managed_node_count=healthy_count,
        )

    def _runtime_snapshot(self, node_id: str):
        return self._runtime_service.get_standalone_addon_runtime_snapshot(node_id)

    def _compose_files_for_snapshot(self, snapshot) -> list[Path]:
        raw_runtime = snapshot.raw_runtime if isinstance(snapshot.raw_runtime, dict) else {}
        compose_files = raw_runtime.get("compose_files_in_use")
        if isinstance(compose_files, list):
            paths = [Path(item) for item in compose_files if isinstance(item, str) and item.strip()]
            if paths:
                return paths
        desired_path = Path(snapshot.desired_path)
        current_compose = desired_path.parent / "current" / "docker-compose.yml"
        version_compose = desired_path.parent / "versions" / str(snapshot.runtime.active_version or "").strip() / "docker-compose.yml"
        if current_compose.exists():
            return [current_compose]
        if version_compose.exists():
            return [version_compose]
        raise ValueError("compose_files_unavailable")

    def _project_name_for_snapshot(self, snapshot) -> str:
        raw_desired = snapshot.raw_desired if isinstance(snapshot.raw_desired, dict) else {}
        runtime_cfg = raw_desired.get("runtime") if isinstance(raw_desired.get("runtime"), dict) else {}
        project_name = str(runtime_cfg.get("project_name") or "").strip()
        if not project_name:
            raise ValueError("project_name_unavailable")
        return project_name

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _boot_log_path(self) -> Path:
        raw = str(getenv("HEXE_SUPERVISOR_BOOT_LOG", "var/supervisor/boot.log")).strip()
        return Path(raw or "var/supervisor/boot.log")

    def _append_boot_log(self, event: str, *, context: dict[str, Any] | None = None) -> None:
        log_path = self._boot_log_path()
        payload: dict[str, Any] = {"event": str(event)}
        if context:
            payload.update(context)
        message = str(payload.get("message") or event).strip()
        omit_keys = {"message"}
        if message == event:
            omit_keys.add("event")
        details = []
        for key in sorted(k for k in payload.keys() if k not in omit_keys):
            details.append(f"{key}={payload.get(key)}")
        suffix = f" | {' '.join(details)}" if details else ""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{ts} [{event}] {message}{suffix}\n")
        except Exception:
            return

    def _set_desired_state(self, snapshot, desired_state: str) -> None:
        if not isinstance(snapshot.raw_desired, dict):
            return
        payload = dict(snapshot.raw_desired)
        payload["desired_state"] = desired_state
        self._write_json(Path(snapshot.desired_path), payload)

    def _set_runtime_state(
        self,
        snapshot,
        runtime_state: str,
        *,
        lifecycle_state: str,
        last_action: str,
        error: str | None = None,
    ) -> None:
        payload = dict(snapshot.raw_runtime) if isinstance(snapshot.raw_runtime, dict) else {}
        payload["state"] = runtime_state
        payload["lifecycle_state"] = lifecycle_state
        payload["last_action"] = last_action
        payload["last_action_at"] = self._now_iso()
        if error:
            payload["error"] = error
            payload["last_error"] = error
        else:
            payload.pop("error", None)
            payload.pop("last_error", None)
        self._write_json(Path(snapshot.runtime_path), payload)

    def _action_result(self, action: str, node_id: str) -> SupervisorNodeActionResult:
        node = next((item for item in self._managed_nodes() if item.node_id == node_id), None)
        if node is None:
            snapshot = self._runtime_snapshot(node_id)
            node = ManagedNodeSummary(
                node_id=snapshot.runtime.addon_id,
                desired_state=snapshot.runtime.desired_state,
                runtime_state=snapshot.runtime.runtime_state,
                health_status=snapshot.runtime.health_status,
                active_version=snapshot.runtime.active_version,
                running=snapshot.runtime.running,
            )
        return SupervisorNodeActionResult(action=action, node=node)

    def start_managed_node(self, node_id: str) -> SupervisorNodeActionResult:
        snapshot = self._runtime_snapshot(node_id)
        compose_files = self._compose_files_for_snapshot(snapshot)
        project_name = self._project_name_for_snapshot(snapshot)
        self._append_boot_log(
            "runtime_action",
            context={"runtime_id": node_id, "action": "start", "scope": "managed_node"},
        )
        self._record_runtime_lifecycle_marker(
            scope="managed_node",
            resource_id=node_id,
            event_type="start_requested",
            message=f"Start requested for {node_id}",
            payload={"runtime_id": node_id, "action": "start"},
        )
        self._set_desired_state(snapshot, "running")
        self._set_runtime_state(snapshot, "running", lifecycle_state="starting", last_action="start")
        try:
            compose_up(compose_files, project_name)
        except Exception as exc:
            self._set_runtime_state(snapshot, "error", lifecycle_state="error", last_action="start", error=str(exc))
            raise
        self._set_runtime_state(snapshot, "running", lifecycle_state="running", last_action="start")
        return self._action_result("start", node_id)

    def stop_managed_node(self, node_id: str) -> SupervisorNodeActionResult:
        snapshot = self._runtime_snapshot(node_id)
        compose_files = self._compose_files_for_snapshot(snapshot)
        project_name = self._project_name_for_snapshot(snapshot)
        self._append_boot_log(
            "runtime_action",
            context={"runtime_id": node_id, "action": "stop", "scope": "managed_node"},
        )
        self._record_runtime_lifecycle_marker(
            scope="managed_node",
            resource_id=node_id,
            event_type="stop_requested",
            message=f"Stop requested for {node_id}",
            payload={"runtime_id": node_id, "action": "stop"},
        )
        self._set_desired_state(snapshot, "stopped")
        self._set_runtime_state(snapshot, "running", lifecycle_state="stopping", last_action="stop")
        try:
            compose_down(compose_files, project_name)
        except Exception as exc:
            self._set_runtime_state(snapshot, "error", lifecycle_state="error", last_action="stop", error=str(exc))
            raise
        self._set_runtime_state(snapshot, "stopped", lifecycle_state="stopped", last_action="stop")
        return self._action_result("stop", node_id)

    def restart_managed_node(self, node_id: str) -> SupervisorNodeActionResult:
        snapshot = self._runtime_snapshot(node_id)
        compose_files = self._compose_files_for_snapshot(snapshot)
        project_name = self._project_name_for_snapshot(snapshot)
        self._append_boot_log(
            "runtime_action",
            context={"runtime_id": node_id, "action": "restart", "scope": "managed_node"},
        )
        self._record_runtime_lifecycle_marker(
            scope="managed_node",
            resource_id=node_id,
            event_type="restart_requested",
            message=f"Restart requested for {node_id}",
            payload={"runtime_id": node_id, "action": "restart"},
        )
        self._set_desired_state(snapshot, "running")
        self._set_runtime_state(snapshot, "running", lifecycle_state="restarting", last_action="restart")
        try:
            compose_down(compose_files, project_name)
            compose_up(compose_files, project_name)
        except Exception as exc:
            self._set_runtime_state(snapshot, "error", lifecycle_state="error", last_action="restart", error=str(exc))
            raise
        self._set_runtime_state(snapshot, "running", lifecycle_state="running", last_action="restart")
        return self._action_result("restart", node_id)

    def _cloudflared_runtime_root(self) -> Path:
        return Path(getenv("HEXE_EDGE_RUNTIME_DIR", Path(os.getcwd()) / "var" / "edge" / "cloudflared"))

    def _cloudflared_provider(self) -> str:
        provider = str(getenv("HEXE_CLOUDFLARED_PROVIDER", "auto")).strip().lower() or "auto"
        if provider in {"disabled", "docker", "binary"}:
            return provider
        return "auto"

    def _cloudflared_container_name(self) -> str:
        return str(getenv("HEXE_CLOUDFLARED_CONTAINER_NAME", "hexe-cloudflared")).strip() or "hexe-cloudflared"

    def _cloudflared_image(self) -> str:
        return str(getenv("HEXE_CLOUDFLARED_IMAGE", "cloudflare/cloudflared:latest")).strip() or "cloudflare/cloudflared:latest"

    def _cloudflared_restart_policy(self) -> str:
        policy = str(getenv("HEXE_CLOUDFLARED_RESTART_POLICY", "unless-stopped")).strip().lower()
        return policy if policy in {"no", "on-failure", "always", "unless-stopped"} else "unless-stopped"

    def _cloudflared_log_path(self) -> Path:
        return self._cloudflared_runtime_root() / "cloudflared.log"

    def _cloudflared_pid_path(self) -> Path:
        return self._cloudflared_runtime_root() / "cloudflared.pid"

    def _cloudflared_env_path(self) -> Path:
        return self._cloudflared_runtime_root() / "cloudflared.env"

    def _cloudflared_systemd_unit_name(self) -> str:
        return str(getenv("HEXE_CLOUDFLARED_SYSTEMD_UNIT", "hexe-cloudflared.service")).strip() or "hexe-cloudflared.service"

    def _cloudflared_systemd_unit_path(self) -> Path:
        unit_name = self._cloudflared_systemd_unit_name()
        return Path.home() / ".config" / "systemd" / "user" / unit_name

    def _docker_available(self) -> bool:
        return shutil.which("docker") is not None

    def _systemctl_user_available(self) -> bool:
        return shutil.which("systemctl") is not None

    def _systemctl_user_cmd(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)

    def _cloudflared_binary_path(self) -> str | None:
        configured = str(getenv("HEXE_CLOUDFLARED_BINARY", "") or "").strip()
        if configured:
            path = Path(configured).expanduser()
            return str(path) if path.is_file() and os.access(path, os.X_OK) else None
        return shutil.which("cloudflared")

    def _cloudflared_binary_available(self) -> bool:
        return self._cloudflared_binary_path() is not None and self._systemctl_user_available()

    def _write_cloudflared_env_file(self, tunnel_token: str) -> Path:
        if any(ch in tunnel_token for ch in "\r\n\0"):
            raise RuntimeError("cloudflare_tunnel_token_invalid")
        env_path = self._cloudflared_env_path()
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(f"TUNNEL_TOKEN={shlex.quote(tunnel_token)}\n", encoding="utf-8")
        env_path.chmod(0o600)
        return env_path

    def _write_cloudflared_systemd_unit(self, *, binary_path: str, log_path: Path, env_path: Path) -> Path:
        runtime_root = self._cloudflared_runtime_root()
        runtime_root.mkdir(parents=True, exist_ok=True)
        log_path.touch(mode=0o600, exist_ok=True)
        unit_path = self._cloudflared_systemd_unit_path()
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(
            "\n".join(
                [
                    "[Unit]",
                    "Description=Hexe native Cloudflared tunnel",
                    "After=network-online.target",
                    "Wants=network-online.target",
                    "",
                    "[Service]",
                    "Type=simple",
                    f"WorkingDirectory={shlex.quote(str(runtime_root))}",
                    f"EnvironmentFile={shlex.quote(str(env_path))}",
                    f"ExecStart={shlex.quote(binary_path)} tunnel --no-autoupdate run",
                    "Restart=always",
                    "RestartSec=5",
                    f"StandardOutput=append:{log_path}",
                    f"StandardError=append:{log_path}",
                    "",
                    "[Install]",
                    "WantedBy=default.target",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return unit_path

    def _cloudflared_systemd_active(self) -> bool:
        result = self._systemctl_user_cmd(["is-active", "--quiet", self._cloudflared_systemd_unit_name()])
        return result.returncode == 0

    def _cloudflared_systemd_main_pid(self) -> int:
        result = self._systemctl_user_cmd(["show", self._cloudflared_systemd_unit_name(), "--property", "MainPID", "--value"])
        if result.returncode != 0:
            return 0
        try:
            return int(str(result.stdout or "").strip() or "0")
        except Exception:
            return 0

    def _write_runtime_payload(self, payload: dict[str, Any]) -> None:
        runtime_path = self._cloudflared_runtime_root() / "runtime.json"
        self._write_json(runtime_path, payload)

    def _read_runtime_payload(self) -> dict[str, Any]:
        runtime_path = self._cloudflared_runtime_root() / "runtime.json"
        if not runtime_path.exists():
            return {}
        try:
            raw = json.loads(runtime_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return raw if isinstance(raw, dict) else {}

    def _docker_cmd(self, args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)

    def _cloudflared_container_exists(self) -> bool:
        if not self._docker_available():
            return False
        result = self._docker_cmd(["ps", "-a", "--filter", f"name=^{self._cloudflared_container_name()}$", "--format", "{{.Names}}"])
        if result.returncode != 0:
            return False
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return self._cloudflared_container_name() in names

    def _cloudflared_container_running(self) -> bool:
        if not self._docker_available():
            return False
        result = self._docker_cmd(["inspect", "-f", "{{.State.Running}}", self._cloudflared_container_name()])
        return result.returncode == 0 and str(result.stdout or "").strip().lower() == "true"

    def _remove_cloudflared_container(self) -> None:
        if self._cloudflared_container_exists():
            self._docker_cmd(["rm", "-f", self._cloudflared_container_name()])

    def _stop_cloudflared_native(self) -> None:
        if self._systemctl_user_available():
            self._systemctl_user_cmd(["disable", "--now", self._cloudflared_systemd_unit_name()])
        pid_path = self._cloudflared_pid_path()
        if pid_path.exists():
            try:
                pid = int(pid_path.read_text(encoding="utf-8").strip())
            except Exception:
                pid = 0
            if pid > 0:
                try:
                    os.kill(pid, 15)
                except ProcessLookupError:
                    pass
                except Exception:
                    pass
        pid_path.unlink(missing_ok=True)
        self._cloudflared_env_path().unlink(missing_ok=True)

    def _ensure_cloudflared_stopped(self) -> None:
        self._remove_cloudflared_container()
        self._stop_cloudflared_native()

    def _cloudflared_runtime_status(self) -> dict[str, Any]:
        root = self._cloudflared_runtime_root()
        runtime_path = root / "runtime.json"
        payload = self._read_runtime_payload()
        if not runtime_path.exists():
            return {"exists": False}
        provider = str(payload.get("provider") or self._cloudflared_provider() or "unknown")
        if provider == "docker":
            if not self._docker_available():
                payload.update({"state": "error", "healthy": False, "last_error": "docker_binary_not_found"})
            elif self._cloudflared_container_running():
                payload.update({"state": "running", "healthy": True, "last_error": None})
            elif self._cloudflared_container_exists():
                inspect = self._docker_cmd(["inspect", "-f", "{{.State.Status}}", self._cloudflared_container_name()])
                payload.update(
                    {
                        "state": str(inspect.stdout or "").strip().lower() or "stopped",
                        "healthy": False,
                        "last_error": str(payload.get("last_error") or "cloudflared_container_not_running"),
                    }
                )
            else:
                payload.update({"state": "stopped", "healthy": False, "last_error": str(payload.get("last_error") or "runtime_not_started")})
        elif provider == "binary":
            running = self._cloudflared_systemd_active() if self._systemctl_user_available() else False
            pid = self._cloudflared_systemd_main_pid() if running else 0
            if pid > 0:
                self._cloudflared_pid_path().write_text(f"{pid}\n", encoding="utf-8")
                payload["pid"] = pid
            else:
                self._cloudflared_pid_path().unlink(missing_ok=True)
                payload.pop("pid", None)
            payload.update(
                {
                    "state": "running" if running else "stopped",
                    "healthy": running,
                    "last_error": None if running else str(payload.get("last_error") or "runtime_not_started"),
                    "systemd_unit": self._cloudflared_systemd_unit_name(),
                    "systemd_unit_path": str(self._cloudflared_systemd_unit_path()),
                }
            )
        payload["exists"] = True
        payload["checked_at"] = self._now_iso()
        raw_usage = payload.get("resource_usage") if isinstance(payload.get("resource_usage"), dict) else {}
        resource_usage, observed_payload = self._observed_resource_view(raw_usage, payload)
        payload = observed_payload
        payload["resource_usage"] = resource_usage
        self._write_runtime_payload(payload)
        return payload

    def apply_cloudflared_config(self, config: dict[str, Any]) -> dict[str, Any]:
        root = self._cloudflared_runtime_root()
        root.mkdir(parents=True, exist_ok=True)
        config_path = root / "config.json"
        config_payload = dict(config)
        config_payload.pop("tunnel-token", None)
        self._write_json(config_path, config_payload)
        desired_enabled = bool(config.get("desired_enabled"))
        tunnel_id = str(config.get("tunnel") or "").strip()
        tunnel_token = str(config.get("tunnel-token") or "").strip()
        provider = self._cloudflared_provider()
        if provider == "auto":
            if self._docker_available():
                provider = "docker"
            elif self._cloudflared_binary_available():
                provider = "binary"
            else:
                provider = "disabled"

        runtime_payload = {
            "runtime_id": "cloudflared",
            "provider": provider,
            "state": "configured",
            "healthy": False,
            "last_action": "reconcile",
            "last_action_at": self._now_iso(),
            "config_path": str(config_path),
            "tunnel_id": tunnel_id or None,
            "container_name": self._cloudflared_container_name() if provider == "docker" else None,
        }

        if not desired_enabled:
            self._ensure_cloudflared_stopped()
            runtime_payload.update({"state": "stopped", "healthy": False, "last_error": None})
            self._write_runtime_payload(runtime_payload)
            return {"ok": True, "runtime_state": "stopped", "config_path": str(config_path)}

        if not tunnel_id:
            runtime_payload.update({"state": "error", "last_error": "cloudflare_tunnel_missing"})
            self._write_runtime_payload(runtime_payload)
            return {"ok": False, "runtime_state": "error", "config_path": str(config_path), "error": "cloudflare_tunnel_missing"}
        if provider == "disabled":
            runtime_payload.update({"state": "configured", "healthy": False, "last_error": "cloudflared_runtime_disabled"})
            self._write_runtime_payload(runtime_payload)
            return {"ok": False, "runtime_state": "configured", "config_path": str(config_path), "error": "cloudflared_runtime_disabled"}
        if not tunnel_token:
            runtime_payload.update({"state": "error", "last_error": "cloudflare_tunnel_token_missing"})
            self._write_runtime_payload(runtime_payload)
            return {"ok": False, "runtime_state": "error", "config_path": str(config_path), "error": "cloudflare_tunnel_token_missing"}

        try:
            self._ensure_cloudflared_stopped()
            if provider == "docker":
                if not self._docker_available():
                    raise RuntimeError("docker_binary_not_found")
                result = self._docker_cmd(
                    [
                        "run",
                        "-d",
                        "--name",
                        self._cloudflared_container_name(),
                        "--network",
                        "host",
                        "--restart",
                        self._cloudflared_restart_policy(),
                        "-e",
                        f"TUNNEL_TOKEN={tunnel_token}",
                        self._cloudflared_image(),
                        "tunnel",
                        "--no-autoupdate",
                        "run",
                    ]
                )
                if result.returncode != 0:
                    raise RuntimeError(str(result.stderr or result.stdout or "cloudflared_docker_run_failed").strip())
                runtime_payload.update(
                    {
                        "state": "running",
                        "healthy": True,
                        "last_error": None,
                        "last_started_at": self._now_iso(),
                        "container_id": str(result.stdout or "").strip() or None,
                    }
                )
            else:
                binary_path = self._cloudflared_binary_path()
                if not binary_path:
                    raise RuntimeError("cloudflared_binary_not_found")
                if not self._systemctl_user_available():
                    raise RuntimeError("systemctl_user_not_available")
                log_path = self._cloudflared_log_path()
                env_path = self._write_cloudflared_env_file(tunnel_token)
                unit_path = self._write_cloudflared_systemd_unit(binary_path=binary_path, log_path=log_path, env_path=env_path)
                reload_result = self._systemctl_user_cmd(["daemon-reload"])
                if reload_result.returncode != 0:
                    raise RuntimeError(str(reload_result.stderr or reload_result.stdout or "cloudflared_systemd_reload_failed").strip())
                start_result = self._systemctl_user_cmd(["enable", "--now", self._cloudflared_systemd_unit_name()])
                if start_result.returncode != 0:
                    raise RuntimeError(str(start_result.stderr or start_result.stdout or "cloudflared_systemd_start_failed").strip())
                pid = self._cloudflared_systemd_main_pid()
                if pid > 0:
                    self._cloudflared_pid_path().write_text(f"{pid}\n", encoding="utf-8")
                runtime_payload.update(
                    {
                        "state": "running",
                        "healthy": True,
                        "last_error": None,
                        "last_started_at": self._now_iso(),
                        "pid": pid or None,
                        "systemd_unit": self._cloudflared_systemd_unit_name(),
                        "systemd_unit_path": str(unit_path),
                    }
                )
        except Exception as exc:
            runtime_payload.update({"state": "error", "healthy": False, "last_error": str(exc) or type(exc).__name__})
            self._write_runtime_payload(runtime_payload)
            return {"ok": False, "runtime_state": runtime_payload["state"], "config_path": str(config_path), "error": runtime_payload["last_error"]}

        self._write_runtime_payload(runtime_payload)
        return {"ok": True, "runtime_state": str(runtime_payload["state"]), "config_path": str(config_path)}

    def get_runtime_state(self, runtime_id: str) -> dict[str, Any]:
        if runtime_id != "cloudflared":
            return {"exists": False}
        return self._cloudflared_runtime_status()

    def health_summary(self) -> SupervisorHealthSummary:
        managed_nodes = self._managed_nodes()
        healthy = sum(1 for item in managed_nodes if str(item.health_status or "").strip().lower() == "healthy")
        unhealthy = sum(1 for item in managed_nodes if str(item.health_status or "").strip().lower() == "unhealthy")
        return SupervisorHealthSummary(
            status="ok",
            host=self._host_identity(),
            resources=self._host_resources(),
            managed_node_count=len(managed_nodes),
            healthy_node_count=healthy,
            unhealthy_node_count=unhealthy,
        )

    def info_summary(self) -> SupervisorInfoSummary:
        managed_nodes = self._managed_nodes()
        host = self._host_identity()
        return SupervisorInfoSummary(
            supervisor_id=self._supervisor_id(),
            host=host,
            resources=self._host_resources(),
            boundaries=SupervisorOwnershipBoundary(
                owns=[
                    "host-local standalone runtime realization",
                    "host-local worker/process execution helpers",
                    "desired-to-runtime reconciliation",
                    "standalone workload lifecycle execution",
                ],
                depends_on_core_for=[
                    "global governance and scheduler policy",
                    "node trust and onboarding authority",
                    "operator UI and control-plane APIs",
                ],
            ),
            managed_node_count=len(managed_nodes),
            managed_nodes=managed_nodes,
        )
