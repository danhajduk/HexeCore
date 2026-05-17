from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_SUPERVISOR_BIND = "127.0.0.1"
DEFAULT_SUPERVISOR_PORT = 57665
DEFAULT_SUPERVISOR_SOCKET = "/run/hexe/supervisor.sock"
DEFAULT_SUPERVISOR_TRANSPORT = "socket"


@dataclass(frozen=True)
class SupervisorApiConfig:
    transport: str
    bind_host: str
    port: int
    unix_socket: str


def _env_text(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = str(raw).strip()
    return value or default


def _env_port(name: str, default: int) -> int:
    raw = os.getenv(name)
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
