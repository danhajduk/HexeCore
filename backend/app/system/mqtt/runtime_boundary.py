from __future__ import annotations

import asyncio
import os
import shutil
import signal
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class BrokerRuntimeStatus:
    provider: str
    state: str
    healthy: bool
    degraded_reason: str | None = None
    checked_at: str = _utcnow_iso()


class BrokerRuntimeBoundary(Protocol):
    async def ensure_running(self) -> BrokerRuntimeStatus: ...

    async def stop(self) -> BrokerRuntimeStatus: ...

    async def health_check(self) -> BrokerRuntimeStatus: ...

    async def reload(self) -> BrokerRuntimeStatus: ...

    async def controlled_restart(self) -> BrokerRuntimeStatus: ...

    async def get_status(self) -> BrokerRuntimeStatus: ...


class InMemoryBrokerRuntimeBoundary:
    def __init__(self, provider: str = "embedded_mosquitto") -> None:
        self._provider = provider
        self._state = "stopped"
        self._healthy = False
        self._degraded_reason: str | None = "runtime_not_started"

    async def ensure_running(self) -> BrokerRuntimeStatus:
        self._state = "running"
        self._healthy = True
        self._degraded_reason = None
        return self._status()

    async def stop(self) -> BrokerRuntimeStatus:
        self._state = "stopped"
        self._healthy = False
        self._degraded_reason = "runtime_stopped"
        return self._status()

    async def health_check(self) -> BrokerRuntimeStatus:
        return self._status()

    async def reload(self) -> BrokerRuntimeStatus:
        if self._state != "running":
            self._healthy = False
            self._degraded_reason = "runtime_not_running"
            return self._status()
        self._healthy = True
        self._degraded_reason = None
        return self._status()

    async def controlled_restart(self) -> BrokerRuntimeStatus:
        self._state = "running"
        self._healthy = True
        self._degraded_reason = None
        return self._status()

    async def get_status(self) -> BrokerRuntimeStatus:
        return self._status()

    def _status(self) -> BrokerRuntimeStatus:
        return BrokerRuntimeStatus(
            provider=self._provider,
            state=self._state,
            healthy=self._healthy,
            degraded_reason=self._degraded_reason,
            checked_at=_utcnow_iso(),
        )


class MosquittoProcessRuntimeBoundary:
    def __init__(
        self,
        *,
        live_dir: str,
        config_filename: str = "broker.conf",
        host: str = "127.0.0.1",
        port: int = 1883,
    ) -> None:
        self._provider = "embedded_mosquitto"
        self._live_dir = os.path.abspath(live_dir)
        self._config_filename = config_filename
        self._host = host
        self._port = int(port)
        self._process: subprocess.Popen[str] | None = None
        self._state = "stopped"
        self._healthy = False
        self._degraded_reason: str | None = "runtime_not_started"

    async def ensure_running(self) -> BrokerRuntimeStatus:
        return await asyncio.to_thread(self._ensure_running_sync)

    async def stop(self) -> BrokerRuntimeStatus:
        return await asyncio.to_thread(self._stop_sync)

    async def health_check(self) -> BrokerRuntimeStatus:
        return await asyncio.to_thread(self._health_check_sync)

    async def reload(self) -> BrokerRuntimeStatus:
        return await asyncio.to_thread(self._reload_sync)

    async def controlled_restart(self) -> BrokerRuntimeStatus:
        return await asyncio.to_thread(self._controlled_restart_sync)

    async def get_status(self) -> BrokerRuntimeStatus:
        return self._status()

    def _ensure_running_sync(self) -> BrokerRuntimeStatus:
        status = self._health_check_sync()
        if status.healthy:
            return status
        return self._start_sync()

    def _stop_sync(self) -> BrokerRuntimeStatus:
        proc = self._process
        self._process = None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        self._state = "stopped"
        self._healthy = False
        self._degraded_reason = "runtime_stopped"
        return self._status()

    def _reload_sync(self) -> BrokerRuntimeStatus:
        proc = self._process
        if proc is None or proc.poll() is not None:
            self._state = "stopped"
            self._healthy = False
            self._degraded_reason = "runtime_not_running"
            return self._status()
        try:
            proc.send_signal(signal.SIGHUP)
        except Exception:
            self._healthy = False
            self._degraded_reason = "reload_signal_failed"
            return self._status()
        return self._health_check_sync()

    def _controlled_restart_sync(self) -> BrokerRuntimeStatus:
        self._stop_sync()
        return self._start_sync()

    def _health_check_sync(self) -> BrokerRuntimeStatus:
        proc = self._process
        if proc is None:
            self._state = "stopped"
            self._healthy = False
            if self._degraded_reason is None:
                self._degraded_reason = "runtime_not_started"
            return self._status()
        if proc.poll() is not None:
            self._state = "stopped"
            self._healthy = False
            self._degraded_reason = f"process_exited:{proc.returncode}"
            return self._status()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        try:
            sock.connect((self._host, self._port))
        except Exception:
            self._state = "running"
            self._healthy = False
            self._degraded_reason = "broker_unreachable"
            return self._status()
        finally:
            sock.close()
        self._state = "running"
        self._healthy = True
        self._degraded_reason = None
        return self._status()

    def _start_sync(self) -> BrokerRuntimeStatus:
        conf_path = os.path.join(self._live_dir, self._config_filename)
        if not os.path.exists(conf_path):
            self._state = "stopped"
            self._healthy = False
            self._degraded_reason = "config_missing"
            return self._status()
        cmd = shutil.which("mosquitto")
        if not cmd:
            self._state = "stopped"
            self._healthy = False
            self._degraded_reason = "mosquitto_binary_not_found"
            return self._status()
        try:
            os.makedirs(self._live_dir, exist_ok=True)
            self._process = subprocess.Popen(
                [cmd, "-c", conf_path],
                cwd=self._live_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except Exception:
            self._state = "stopped"
            self._healthy = False
            self._degraded_reason = "runtime_start_failed"
            self._process = None
            return self._status()
        return self._health_check_sync()

    def _status(self) -> BrokerRuntimeStatus:
        return BrokerRuntimeStatus(
            provider=self._provider,
            state=self._state,
            healthy=self._healthy,
            degraded_reason=self._degraded_reason,
            checked_at=_utcnow_iso(),
        )
