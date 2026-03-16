from __future__ import annotations

import os
import socket

from app.system.runtime import StandaloneRuntimeService


class SupervisorDomainService:
    def __init__(self, runtime_service: StandaloneRuntimeService | None = None) -> None:
        self._runtime_service = runtime_service or StandaloneRuntimeService()

    def health_summary(self) -> dict[str, object]:
        runtimes = self._runtime_service.list_standalone_addon_runtimes()
        healthy = sum(1 for item in runtimes if str(item.health_status or "").strip().lower() == "healthy")
        unhealthy = sum(1 for item in runtimes if str(item.health_status or "").strip().lower() == "unhealthy")
        return {
            "status": "ok",
            "managed_node_count": len(runtimes),
            "healthy_node_count": healthy,
            "unhealthy_node_count": unhealthy,
        }

    def info_summary(self) -> dict[str, object]:
        runtimes = self._runtime_service.list_standalone_addon_runtimes()
        return {
            "supervisor_id": socket.gethostname(),
            "runtime_provider": str(os.getenv("SYNTHIA_MQTT_RUNTIME_PROVIDER", "docker")).strip().lower() or "docker",
            "managed_runtime_type": "standalone_addons",
            "managed_node_count": len(runtimes),
            "managed_nodes": [item.addon_id for item in runtimes],
        }
