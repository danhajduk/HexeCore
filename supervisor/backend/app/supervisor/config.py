from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.env import getenv


DEFAULT_SUPERVISOR_BIND = "127.0.0.1"
DEFAULT_SUPERVISOR_PORT = 57665
DEFAULT_SUPERVISOR_SOCKET = "/run/hexe/supervisor.sock"
DEFAULT_SUPERVISOR_TRANSPORT = "socket"
SUPERVISOR_CONFIG_RELATIVE_PATH = Path("config") / "supervisor.json"


@dataclass(frozen=True)
class SupervisorApiConfig:
    transport: str
    bind_host: str
    port: int
    unix_socket: str


def _env_text(name: str, default: str) -> str:
    raw = getenv(name)
    if raw is None:
        return default
    value = str(raw).strip()
    return value or default


def _env_port(name: str, default: int) -> int:
    raw = getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        parsed = int(str(raw).strip())
    except Exception:
        return default
    if parsed <= 0 or parsed > 65535:
        return default
    return parsed


def supervisor_api_config() -> SupervisorApiConfig:
    transport = _env_text("HEXE_SUPERVISOR_TRANSPORT", DEFAULT_SUPERVISOR_TRANSPORT).lower()
    if transport not in {"socket", "http"}:
        transport = DEFAULT_SUPERVISOR_TRANSPORT
    return SupervisorApiConfig(
        transport=transport,
        bind_host=_env_text("HEXE_SUPERVISOR_BIND", DEFAULT_SUPERVISOR_BIND),
        port=_env_port("HEXE_SUPERVISOR_PORT", DEFAULT_SUPERVISOR_PORT),
        unix_socket=_env_text("HEXE_SUPERVISOR_SOCKET", DEFAULT_SUPERVISOR_SOCKET),
    )


def supervisor_install_root() -> Path:
    return Path(__file__).resolve().parents[3]


def supervisor_package_config_path(install_root: Path | None = None) -> Path:
    return (install_root or supervisor_install_root()) / SUPERVISOR_CONFIG_RELATIVE_PATH


def read_supervisor_package_config(install_root: Path | None = None) -> dict[str, Any]:
    path = supervisor_package_config_path(install_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def supervisor_reported_version(install_root: Path | None = None) -> str | None:
    payload = read_supervisor_package_config(install_root)
    value = str(payload.get("version") or "").strip()
    if value:
        return value
    fallback = getenv("HEXE_CORE_VERSION")
    fallback_text = str(fallback or "").strip()
    return fallback_text or None
