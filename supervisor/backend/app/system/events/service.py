from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from typing import Any, Awaitable, Callable

from app.system.security import redact_secrets

from .models import PlatformEvent

log = logging.getLogger("synthia.events")

EventPublisher = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class PlatformEventService:
    def __init__(self, *, max_events: int | None = None, mqtt_publish: EventPublisher | None = None) -> None:
        configured_limit = int(os.getenv("SYNTHIA_EVENTS_MAX_RECENT", "200"))
        self._max_events = max(10, int(max_events or configured_limit))
        self._mqtt_publish = mqtt_publish
        self._events: deque[PlatformEvent] = deque(maxlen=self._max_events)
        self._lock = asyncio.Lock()

    async def emit(self, *, event_type: str, source: str, payload: dict[str, Any] | None = None) -> PlatformEvent:
        event = PlatformEvent(
            event_type=event_type.strip(),
            source=source.strip(),
            payload=redact_secrets(payload or {}),
        )
        async with self._lock:
            self._events.appendleft(event)
        log.info("platform_event type=%s source=%s payload=%s", event.event_type, event.source, event.payload)
        if self._mqtt_publish is not None:
            try:
                await self._mqtt_publish(
                    f"hexe/events/{event.event_type}",
                    event.model_dump(mode="json"),
                )
            except Exception:
                log.exception("Failed to publish platform event over MQTT")
        return event

    async def recent(self, *, limit: int = 100, event_type: str | None = None, source: str | None = None) -> list[dict[str, Any]]:
        cap = max(1, min(self._max_events, int(limit)))
        type_filter = event_type.strip() if isinstance(event_type, str) and event_type.strip() else None
        source_filter = source.strip() if isinstance(source, str) and source.strip() else None
        async with self._lock:
            items = [item.model_dump(mode="json") for item in self._events]
        if type_filter:
            items = [item for item in items if str(item.get("event_type")) == type_filter]
        if source_filter:
            items = [item for item in items if str(item.get("source")) == source_filter]
        return items[:cap]
