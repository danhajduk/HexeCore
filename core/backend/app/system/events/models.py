from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlatformEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str = Field(..., min_length=1)
    timestamp: str = Field(default_factory=_utcnow_iso)
    source: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
