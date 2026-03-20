from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.system.settings.store import SettingsStore


DEFAULT_PLATFORM_NAME = "Hexe AI"
DEFAULT_PLATFORM_SHORT = "Hexe"
DEFAULT_PLATFORM_DOMAIN = "hexe-ai.com"


@dataclass(frozen=True)
class PlatformIdentity:
    platform_name: str
    platform_short: str
    platform_domain: str
    core_name: str

    def to_dict(self) -> dict[str, str]:
        return {
            "platform_name": self.platform_name,
            "platform_short": self.platform_short,
            "platform_domain": self.platform_domain,
            "core_name": self.core_name,
        }


async def load_platform_identity(settings_store: SettingsStore | None = None) -> PlatformIdentity:
    values: dict[str, Any] = {}
    if settings_store is not None:
        try:
            values = await settings_store.get_all()
        except Exception:
            values = {}
    return platform_identity_from_values(values)


def platform_identity_from_values(values: dict[str, Any] | None = None) -> PlatformIdentity:
    data = values if isinstance(values, dict) else {}
    platform_name = _pick_text(
        data.get("platform.name"),
        os.getenv("PLATFORM_NAME"),
        DEFAULT_PLATFORM_NAME,
    )
    platform_short = _pick_text(
        data.get("platform.short"),
        os.getenv("PLATFORM_SHORT"),
        DEFAULT_PLATFORM_SHORT,
    )
    platform_domain = _pick_text(
        data.get("platform.domain"),
        os.getenv("PLATFORM_DOMAIN"),
        DEFAULT_PLATFORM_DOMAIN,
    )
    core_name = _pick_text(
        data.get("app.name"),
        data.get("platform.core_name"),
        os.getenv("PLATFORM_CORE_NAME"),
        f"{platform_short} Core",
    )
    return PlatformIdentity(
        platform_name=platform_name,
        platform_short=platform_short,
        platform_domain=platform_domain,
        core_name=core_name,
    )


def default_platform_identity() -> PlatformIdentity:
    return platform_identity_from_values({})


def _pick_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
