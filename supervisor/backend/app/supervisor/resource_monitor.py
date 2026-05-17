from __future__ import annotations

import copy
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import psutil


class SupervisorResourceMonitor:
    """Samples host-local resources for Supervisor-owned runtime identities."""

    def __init__(
        self,
        *,
        process_factory: Callable[[int], Any] | None = None,
        command_runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
        docker_available: Callable[[], bool] | None = None,
        systemctl_available: Callable[[], bool] | None = None,
    ) -> None:
        self._process_factory = process_factory or psutil.Process
        self._command_runner = command_runner or self._run_command
        self._docker_available = docker_available or (lambda: shutil.which("docker") is not None)
        self._systemctl_available = systemctl_available or (lambda: shutil.which("systemctl") is not None)

    def enrich(
        self,
        resource_usage: dict[str, object] | None,
        runtime_metadata: dict[str, object] | None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        usage = dict(resource_usage or {})
        metadata = copy.deepcopy(runtime_metadata or {})
        metadata.setdefault("resource_observer", "supervisor")

        top_metrics = self._sample_target(metadata)
        if top_metrics:
            self._merge_metrics(usage, top_metrics)

        service_metrics = self._enrich_services(metadata.get("services"))
        container_metrics = self._enrich_containers(metadata.get("containers"))

        aggregate = self._aggregate_metrics([*service_metrics, *container_metrics])
        if aggregate:
            self._merge_metrics(usage, aggregate)

        if "sampled_at" not in usage and (top_metrics or aggregate):
            usage["sampled_at"] = self._now_iso()
            usage.setdefault("resource_observer", "supervisor")
        return usage, metadata

    def _run_command(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5.0, check=False)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _as_pid(self, value: object) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            pid = int(value)  # type: ignore[arg-type]
        except Exception:
            return None
        return pid if pid > 0 else None

    def _first_text(self, target: dict[str, object], keys: list[str]) -> str | None:
        for key in keys:
            value = target.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _process_metrics(self, pid: int) -> dict[str, object]:
        try:
            proc = self._process_factory(pid)
            try:
                cpu_percent = float(proc.cpu_percent(interval=None))
            except Exception:
                cpu_percent = None
            try:
                mem_percent = float(proc.memory_percent())
            except Exception:
                mem_percent = None
            try:
                rss_bytes = int(proc.memory_info().rss)
            except Exception:
                rss_bytes = None
            try:
                status = str(proc.status())
            except Exception:
                status = None
            metrics: dict[str, object] = {
                "pid": pid,
                "resource_source": "supervisor_pid",
                "sampled_at": self._now_iso(),
            }
            if cpu_percent is not None:
                metrics["cpu_percent"] = cpu_percent
            if mem_percent is not None:
                metrics["mem_percent"] = mem_percent
            if rss_bytes is not None:
                metrics["rss_bytes"] = rss_bytes
            if status:
                metrics["process_status"] = status
            return metrics
        except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
            return {
                "pid": pid,
                "running": False,
                "resource_source": "supervisor_pid",
                "last_error": "process_unavailable",
                "sampled_at": self._now_iso(),
            }
        except Exception as exc:
            return {
                "pid": pid,
                "resource_source": "supervisor_pid",
                "last_error": str(exc) or type(exc).__name__,
                "sampled_at": self._now_iso(),
            }

    def _systemd_main_pid(self, unit: str) -> int | None:
        if not self._systemctl_available():
            return None
        try:
            result = self._command_runner(["systemctl", "--user", "show", unit, "--property=MainPID", "--value"])
        except Exception:
            return None
        if result.returncode != 0:
            return None
        return self._as_pid(str(result.stdout or "").strip())

    def _docker_stats(self, identifiers: list[str]) -> dict[str, dict[str, object]]:
        names = [item for item in dict.fromkeys(str(value or "").strip() for value in identifiers) if item]
        if not names or not self._docker_available():
            return {}
        try:
            result = self._command_runner(
                [
                    "docker",
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{.Name}}\t{{.ID}}\t{{.CPUPerc}}\t{{.MemPerc}}",
                    *names,
                ]
            )
        except Exception:
            return {}
        if result.returncode != 0:
            return {}
        stats: dict[str, dict[str, object]] = {}
        for line in (result.stdout or "").splitlines():
            parts = [chunk.strip() for chunk in line.split("\t")]
            if len(parts) < 4:
                continue
            name, container_id, cpu_raw, mem_raw = parts[0], parts[1], parts[2], parts[3]
            metrics: dict[str, object] = {
                "container_name": name,
                "container_id": container_id,
                "resource_source": "supervisor_docker",
                "sampled_at": self._now_iso(),
            }
            try:
                metrics["cpu_percent"] = float(cpu_raw.replace("%", "").strip())
            except Exception:
                pass
            try:
                metrics["mem_percent"] = float(mem_raw.replace("%", "").strip())
            except Exception:
                pass
            stats[name] = metrics
            if container_id:
                stats[container_id] = metrics
        return stats

    def _sample_container(self, target: dict[str, object]) -> dict[str, object]:
        identifier = self._first_text(target, ["container_name", "container_id", "name"])
        if not identifier:
            return {}
        return dict(self._docker_stats([identifier]).get(identifier) or {})

    def _sample_target(self, target: object) -> dict[str, object]:
        if not isinstance(target, dict):
            return {}

        pid = self._as_pid(target.get("pid"))
        process = target.get("process")
        if pid is None and isinstance(process, dict):
            pid = self._as_pid(process.get("pid"))

        systemd_unit = self._first_text(target, ["systemd_unit", "systemd_service"])
        if pid is None and systemd_unit:
            pid = self._systemd_main_pid(systemd_unit)
            if pid is not None:
                target["pid"] = pid

        if pid is not None:
            metrics = self._process_metrics(pid)
            self._merge_metrics(target, metrics)
            if systemd_unit:
                target.setdefault("resource_source", "supervisor_systemd_pid")
                metrics.setdefault("resource_source", "supervisor_systemd_pid")
            return metrics

        container_metrics = self._sample_container(target)
        if container_metrics:
            self._merge_metrics(target, container_metrics)
        return container_metrics

    def _enrich_services(self, services: object) -> list[dict[str, object]]:
        metrics: list[dict[str, object]] = []
        if isinstance(services, list):
            for item in services:
                sampled = self._sample_target(item)
                if sampled:
                    metrics.append(sampled)
        elif isinstance(services, dict):
            for item in services.values():
                sampled = self._sample_target(item)
                if sampled:
                    metrics.append(sampled)
        return metrics

    def _enrich_containers(self, containers: object) -> list[dict[str, object]]:
        metrics: list[dict[str, object]] = []
        if not isinstance(containers, list):
            return metrics
        identifiers: list[str] = []
        for item in containers:
            if isinstance(item, dict):
                identifier = self._first_text(item, ["container_name", "container_id", "name"])
                if identifier:
                    identifiers.append(identifier)
        stats = self._docker_stats(identifiers)
        for item in containers:
            if not isinstance(item, dict):
                continue
            identifier = self._first_text(item, ["container_name", "container_id", "name"])
            sampled = dict(stats.get(identifier or "") or {})
            if sampled:
                self._merge_metrics(item, sampled)
                metrics.append(sampled)
        return metrics

    def _merge_metrics(self, target: dict[str, object], metrics: dict[str, object]) -> None:
        for key, value in metrics.items():
            if value is not None:
                target[key] = value

    def _aggregate_metrics(self, entries: list[dict[str, object]]) -> dict[str, object]:
        if not entries:
            return {}
        cpu_total = 0.0
        mem_total = 0.0
        rss_total = 0
        cpu_seen = False
        mem_seen = False
        rss_seen = False
        for entry in entries:
            cpu = entry.get("cpu_percent")
            mem = entry.get("mem_percent")
            rss = entry.get("rss_bytes")
            if isinstance(cpu, int | float):
                cpu_total += float(cpu)
                cpu_seen = True
            if isinstance(mem, int | float):
                mem_total += float(mem)
                mem_seen = True
            if isinstance(rss, int):
                rss_total += rss
                rss_seen = True
        aggregate: dict[str, object] = {
            "resource_source": "supervisor_aggregate",
            "sampled_at": self._now_iso(),
        }
        if cpu_seen:
            aggregate["cpu_percent"] = cpu_total
        if mem_seen:
            aggregate["mem_percent"] = mem_total
        if rss_seen:
            aggregate["rss_bytes"] = rss_total
        return aggregate
