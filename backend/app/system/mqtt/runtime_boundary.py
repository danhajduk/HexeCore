from __future__ import annotations

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
