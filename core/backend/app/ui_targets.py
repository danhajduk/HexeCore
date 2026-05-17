from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.ui_metadata import normalize_ui_base_url


UiTargetKind = Literal["node", "addon"]


@dataclass(frozen=True)
class UiProxyTarget:
    kind: UiTargetKind
    target_id: str
    public_prefix: str
    ui_enabled: bool
    ui_base_url: str | None
    ui_health_endpoint: str | None = None
    ui_supports_prefix: bool | None = None
    ui_entry_path: str | None = None


@dataclass(frozen=True)
class UiProxyAvailability:
    available: bool
    status_code: int
    detail: str
    ui_base_url: str | None = None
    ui_health_endpoint: str | None = None


def validate_ui_proxy_target(target: UiProxyTarget) -> UiProxyAvailability:
    prefix = f"{target.kind}_ui"
    if not target.ui_enabled:
        return UiProxyAvailability(False, 404, f"{prefix}_not_enabled")

    try:
        normalized_base = normalize_ui_base_url(target.ui_base_url)
    except ValueError:
        return UiProxyAvailability(False, 502, f"{prefix}_endpoint_invalid")
    if not normalized_base:
        return UiProxyAvailability(False, 404, f"{prefix}_endpoint_not_configured")

    if target.ui_supports_prefix is False:
        return UiProxyAvailability(False, 409, f"{prefix}_prefix_not_supported")

    entry_path = str(target.ui_entry_path or "").strip()
    if entry_path:
        if entry_path.startswith(("http://", "https://")):
            return UiProxyAvailability(False, 409, f"{prefix}_entry_path_invalid")
        if not entry_path.startswith("/"):
            return UiProxyAvailability(False, 409, f"{prefix}_entry_path_invalid")

    health_endpoint = None
    if target.ui_health_endpoint:
        try:
            health_endpoint = normalize_ui_base_url(target.ui_health_endpoint)
        except ValueError:
            return UiProxyAvailability(False, 502, f"{prefix}_health_endpoint_invalid")

    return UiProxyAvailability(
        True,
        200,
        "ok",
        ui_base_url=normalized_base,
        ui_health_endpoint=health_endpoint,
    )
