from __future__ import annotations

from typing import Any

from .models import EdgeTunnelStatus, utcnow_iso


def merge_cloudflared_runtime_status(
    tunnel_status: EdgeTunnelStatus,
    runtime_payload: dict[str, Any] | None,
) -> EdgeTunnelStatus:
    if not isinstance(runtime_payload, dict) or not bool(runtime_payload.get("exists")):
        return tunnel_status

    runtime_state = str(runtime_payload.get("state") or runtime_payload.get("runtime_state") or "").strip()
    if not runtime_state:
        runtime_state = tunnel_status.runtime_state

    update: dict[str, Any] = {
        "configured": True,
        "runtime_state": runtime_state,
        "healthy": bool(runtime_payload.get("healthy")),
        "last_error": runtime_payload.get("last_error"),
        "updated_at": utcnow_iso(),
    }
    for source_key, target_key in (
        ("tunnel_id", "tunnel_id"),
        ("tunnel_name", "tunnel_name"),
        ("config_path", "config_path"),
        ("last_started_at", "last_started_at"),
    ):
        value = runtime_payload.get(source_key)
        if value is not None:
            update[target_key] = str(value)
    return tunnel_status.model_copy(update=update)
