from __future__ import annotations

from fastapi import APIRouter, Query

from .service import PlatformEventService


def build_events_router(events: PlatformEventService) -> APIRouter:
    router = APIRouter()

    @router.get("/events")
    async def list_events(
        limit: int = Query(default=100, ge=1, le=1000),
        event_type: str | None = Query(default=None),
        source: str | None = Query(default=None),
    ):
        items = await events.recent(limit=limit, event_type=event_type, source=source)
        return {"ok": True, "items": items}

    return router
