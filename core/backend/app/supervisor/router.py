from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from .models import (
    HostResourceSummary,
    ManagedNodeSummary,
    SupervisorAdmissionContextSummary,
    SupervisorBluetoothBleScanRequest,
    SupervisorBluetoothLeaseRequest,
    SupervisorCoreRuntimeActionResult,
    SupervisorCoreRuntimeHeartbeatRequest,
    SupervisorCoreRuntimeRegistrationRequest,
    SupervisorCoreRuntimeSummary,
    SupervisorHealthSummary,
    SupervisorInfoSummary,
    SupervisorNodeActionResult,
    SupervisorNodeServiceActionResult,
    SupervisorNodeServicesSummary,
    SupervisorRegisteredRuntimeSummary,
    SupervisorRuntimeActionResult,
    SupervisorRuntimeHeartbeatRequest,
    SupervisorRuntimeRegistrationRequest,
    SupervisorRuntimeSummary,
)
from .service import SupervisorDomainService


def build_supervisor_router(service: SupervisorDomainService | None = None) -> APIRouter:
    router = APIRouter(tags=["supervisor"])
    supervisor = service or SupervisorDomainService()

    @router.get("/supervisor/health")
    def get_supervisor_health() -> SupervisorHealthSummary:
        return supervisor.health_summary()

    @router.get("/supervisor/info")
    def get_supervisor_info() -> SupervisorInfoSummary:
        return supervisor.info_summary()

    @router.get("/supervisor/resources")
    def get_supervisor_resources() -> HostResourceSummary:
        return supervisor.resources_summary()

    @router.post("/supervisor/hardware/bluetooth/ble/status")
    def get_supervisor_bluetooth_ble_status(body: SupervisorBluetoothLeaseRequest) -> dict[str, Any]:
        return supervisor.bluetooth_ble_status(body)

    @router.post("/supervisor/hardware/bluetooth/ble/scan")
    def scan_supervisor_bluetooth_ble(body: SupervisorBluetoothBleScanRequest) -> dict[str, Any]:
        return supervisor.bluetooth_ble_scan(body)

    @router.get("/supervisor/resources/history")
    def get_supervisor_resource_history(range: str = "24h", step: str | None = "60s") -> dict[str, Any]:  # noqa: A002
        return supervisor.resource_history(range_value=range, step_value=step)

    @router.get("/supervisor/resources/history/maintenance")
    def get_supervisor_resource_history_maintenance() -> dict[str, Any]:
        return supervisor.resource_history_status()

    @router.post("/supervisor/resources/history/maintenance")
    def maintain_supervisor_resource_history(body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
        payload = body or {}
        return supervisor.maintain_resource_history(action=str(payload.get("action") or "compact"))

    @router.get("/supervisor/runtime")
    def get_supervisor_runtime() -> SupervisorRuntimeSummary:
        return supervisor.runtime_summary()

    @router.get("/supervisor/runtime/{runtime_id}")
    def get_supervisor_runtime_state(runtime_id: str) -> dict[str, Any]:
        return supervisor.get_runtime_state(runtime_id)

    @router.post("/supervisor/runtime/{runtime_id}/apply")
    def apply_supervisor_runtime(runtime_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        if runtime_id != "cloudflared":
            return {"ok": False, "runtime_state": "unsupported", "error": "runtime_not_supported"}
        return supervisor.apply_cloudflared_config(body)

    @router.get("/supervisor/admission")
    def get_supervisor_admission(
        total_capacity_units: int = 100,
        reserve_units: int = 5,
        headroom_pct: float = 0.05,
    ) -> SupervisorAdmissionContextSummary:
        return supervisor.admission_summary(
            total_capacity_units=total_capacity_units,
            reserve_units=reserve_units,
            headroom_pct=headroom_pct,
        )

    @router.get("/supervisor/boot/status")
    def get_supervisor_boot_status() -> dict[str, Any]:
        return supervisor.boot_loop_status()

    @router.post("/supervisor/boot/run")
    def run_supervisor_boot_loop() -> dict[str, Any]:
        return supervisor.run_boot_loop()

    @router.get("/supervisor/nodes")
    def list_supervisor_nodes() -> dict[str, list[ManagedNodeSummary]]:
        return {"items": supervisor.list_managed_nodes()}

    @router.post("/supervisor/nodes/{node_id}/start")
    def start_supervisor_node(node_id: str) -> SupervisorNodeActionResult:
        return supervisor.start_managed_node(node_id)

    @router.post("/supervisor/nodes/{node_id}/stop")
    def stop_supervisor_node(node_id: str) -> SupervisorNodeActionResult:
        return supervisor.stop_managed_node(node_id)

    @router.post("/supervisor/nodes/{node_id}/restart")
    def restart_supervisor_node(node_id: str) -> SupervisorNodeActionResult:
        return supervisor.restart_managed_node(node_id)

    @router.post("/supervisor/runtimes/register")
    def register_supervisor_runtime(body: SupervisorRuntimeRegistrationRequest) -> SupervisorRegisteredRuntimeSummary:
        return supervisor.register_runtime(body)

    @router.post("/supervisor/runtimes/heartbeat")
    def heartbeat_supervisor_runtime(body: SupervisorRuntimeHeartbeatRequest) -> SupervisorRegisteredRuntimeSummary:
        return supervisor.heartbeat_runtime(body)

    @router.get("/supervisor/runtimes")
    def list_supervisor_runtimes() -> dict[str, list[SupervisorRegisteredRuntimeSummary]]:
        return {"items": supervisor.list_registered_runtimes()}

    @router.get("/supervisor/runtimes/{node_id}")
    def get_supervisor_runtime(node_id: str) -> dict[str, SupervisorRegisteredRuntimeSummary]:
        return {"runtime": supervisor.get_registered_runtime(node_id)}

    @router.get("/supervisor/runtimes/{node_id}/resources/history")
    def get_supervisor_runtime_resource_history(node_id: str, range: str = "24h", step: str | None = "60s") -> dict[str, Any]:  # noqa: A002
        return supervisor.runtime_resource_history(node_id, range_value=range, step_value=step)

    @router.post("/supervisor/runtimes/{node_id}/start")
    def start_supervisor_runtime(node_id: str) -> SupervisorRuntimeActionResult:
        return supervisor.start_registered_runtime(node_id)

    @router.post("/supervisor/runtimes/{node_id}/stop")
    def stop_supervisor_runtime(node_id: str) -> SupervisorRuntimeActionResult:
        return supervisor.stop_registered_runtime(node_id)

    @router.post("/supervisor/runtimes/{node_id}/restart")
    def restart_supervisor_runtime(node_id: str) -> SupervisorRuntimeActionResult:
        return supervisor.restart_registered_runtime(node_id)

    @router.get("/supervisor/runtimes/{node_id}/services/status")
    def get_supervisor_node_services(node_id: str) -> SupervisorNodeServicesSummary:
        return supervisor.node_services_status(node_id)

    @router.post("/supervisor/runtimes/{node_id}/services/{service_id}/start")
    def start_supervisor_node_service(node_id: str, service_id: str) -> SupervisorNodeServiceActionResult:
        return supervisor.node_service_action(node_id, service_id=service_id, action="start")

    @router.post("/supervisor/runtimes/{node_id}/services/{service_id}/stop")
    def stop_supervisor_node_service(node_id: str, service_id: str) -> SupervisorNodeServiceActionResult:
        return supervisor.node_service_action(node_id, service_id=service_id, action="stop")

    @router.post("/supervisor/runtimes/{node_id}/services/{service_id}/restart")
    def restart_supervisor_node_service(node_id: str, service_id: str) -> SupervisorNodeServiceActionResult:
        return supervisor.node_service_action(node_id, service_id=service_id, action="restart")

    @router.post("/supervisor/core/runtimes/register")
    def register_core_runtime(body: SupervisorCoreRuntimeRegistrationRequest) -> SupervisorCoreRuntimeSummary:
        return supervisor.register_core_runtime(body)

    @router.post("/supervisor/core/runtimes/heartbeat")
    def heartbeat_core_runtime(body: SupervisorCoreRuntimeHeartbeatRequest) -> SupervisorCoreRuntimeSummary:
        return supervisor.heartbeat_core_runtime(body)

    @router.get("/supervisor/core/runtimes")
    def list_core_runtimes() -> dict[str, list[SupervisorCoreRuntimeSummary]]:
        return {"items": supervisor.list_core_runtimes()}

    @router.get("/supervisor/core/runtimes/{runtime_id}")
    def get_core_runtime(runtime_id: str) -> dict[str, SupervisorCoreRuntimeSummary]:
        return {"runtime": supervisor.get_core_runtime(runtime_id)}

    @router.get("/supervisor/core/runtimes/{runtime_id}/resources/history")
    def get_supervisor_core_runtime_resource_history(runtime_id: str, range: str = "24h", step: str | None = "60s") -> dict[str, Any]:  # noqa: A002
        return supervisor.core_runtime_resource_history(runtime_id, range_value=range, step_value=step)

    @router.post("/supervisor/core/runtimes/{runtime_id}/start")
    def start_core_runtime(runtime_id: str) -> SupervisorCoreRuntimeActionResult:
        return supervisor.start_core_runtime(runtime_id)

    @router.post("/supervisor/core/runtimes/{runtime_id}/stop")
    def stop_core_runtime(runtime_id: str) -> SupervisorCoreRuntimeActionResult:
        return supervisor.stop_core_runtime(runtime_id)

    @router.post("/supervisor/core/runtimes/{runtime_id}/restart")
    def restart_core_runtime(runtime_id: str) -> SupervisorCoreRuntimeActionResult:
        return supervisor.restart_core_runtime(runtime_id)

    return router
