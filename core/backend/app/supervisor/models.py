from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.system.hardware import (
    BLE_PROVISIONING_CONTRACT_VERSION,
    BLE_PROVISIONING_ENVELOPE_SCHEMA_VERSION,
    VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID,
)


class HostIdentitySummary(BaseModel):
    host_id: str
    hostname: str
    runtime_provider: str
    managed_runtime_type: str = "standalone_addons"


class HostResourceSummary(BaseModel):
    uptime_s: float = Field(ge=0)
    load_1m: float = Field(ge=0)
    load_5m: float = Field(ge=0)
    load_15m: float = Field(ge=0)
    cpu_percent_total: float = Field(ge=0, le=100)
    cpu_cores_logical: int = Field(ge=0)
    memory_total_bytes: int = Field(ge=0)
    memory_available_bytes: int = Field(ge=0)
    memory_percent: float = Field(ge=0, le=100)
    root_disk_total_bytes: int | None = Field(default=None, ge=0)
    root_disk_free_bytes: int | None = Field(default=None, ge=0)
    root_disk_percent: float | None = Field(default=None, ge=0, le=100)
    gpu_count: int = Field(default=0, ge=0)
    gpu_utilization_percent: float | None = Field(default=None, ge=0, le=100)
    gpu_memory_percent: float | None = Field(default=None, ge=0, le=100)
    gpu_devices: list[dict[str, object]] = Field(default_factory=list)
    cuda_available: bool = False
    cuda_version: str | None = None
    bluetooth_present: bool = False
    bluetooth_powered: bool = False
    bluetooth_ensure_powered: bool = False
    bluetooth_power_error: str | None = None
    bluetooth_adapters: list[dict[str, object]] = Field(default_factory=list)
    network_rx_Bps: float | None = Field(default=None, ge=0)
    network_tx_Bps: float | None = Field(default=None, ge=0)
    network_bytes_recv: int | None = Field(default=None, ge=0)
    network_bytes_sent: int | None = Field(default=None, ge=0)
    network_errin: int | None = Field(default=None, ge=0)
    network_errout: int | None = Field(default=None, ge=0)
    network_dropin: int | None = Field(default=None, ge=0)
    network_dropout: int | None = Field(default=None, ge=0)
    network_primary_interface: str | None = None
    network_primary_type: str = "unknown"
    network_link_speed_mbps: int | None = Field(default=None, ge=0)
    wifi_signal_percent: float | None = Field(default=None, ge=0, le=100)
    internet_reachable: bool | None = None
    internet_check_error: str | None = None


class SupervisorBluetoothLeaseRequest(BaseModel):
    node_id: str = Field(..., min_length=1)
    lease_token: str = Field(..., min_length=1)
    adapter: str | None = None


class SupervisorBluetoothBleScanRequest(SupervisorBluetoothLeaseRequest):
    service_uuid: str | None = Field(default=None, min_length=4, max_length=64)
    scan_seconds: int = Field(default=5, ge=1, le=60)


class SupervisorBluetoothBleIdentityRequest(SupervisorBluetoothLeaseRequest):
    target_address: str = Field(..., min_length=1, max_length=64)
    timeout_s: int = Field(default=20, ge=1, le=60)


class SupervisorBluetoothPairingAdvertStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_token: str = Field(..., min_length=1)
    adapter: str | None = None
    onboarding_session_id: str = Field(..., min_length=1)
    session_hint: str = Field(..., min_length=6, max_length=32)
    expires_at: str = Field(..., min_length=1)
    node_profile_id: Literal["voice"] = "voice"
    payload_schema_id: Literal["hexe.voice_node.wifi_backend.v1"] = VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID
    claim_code_required: bool = False
    reason: str | None = Field(default=None, max_length=240)


class SupervisorBluetoothPairingAdvertStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_token: str = Field(..., min_length=1)
    adapter: str | None = None
    onboarding_session_id: str = Field(..., min_length=1)


class SupervisorBluetoothPairingAdvertStopRequest(SupervisorBluetoothPairingAdvertStatusRequest):
    reason: str | None = Field(default=None, max_length=240)


class SupervisorBluetoothPairingEndpointIdentityRequest(SupervisorBluetoothPairingAdvertStatusRequest):
    contract_version: Literal["1.0"] = BLE_PROVISIONING_CONTRACT_VERSION
    device_id: str = Field(..., min_length=1, max_length=128)
    node_hardware_id: str = Field(..., min_length=1, max_length=128)
    target_node_id: str = Field(..., min_length=1, max_length=128)
    board_profile: str = Field(..., min_length=1, max_length=80)
    firmware_version: str = Field(..., min_length=1, max_length=120)
    application_type: str = Field(..., min_length=1, max_length=80)
    provisioning_mode: str = Field(..., min_length=1, max_length=80)
    endpoint_ephemeral_public_key: str = Field(..., min_length=43, max_length=128)
    supported_payload_schemas: list[str] = Field(..., min_length=1)
    provisioning_state: str = Field(..., min_length=1, max_length=80)


class SupervisorVoiceWifiProvisioningPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wifi_ssid: str = Field(..., min_length=1, max_length=32)
    wifi_password: str | None = Field(default=None, min_length=8, max_length=63)
    backend_host: str = Field(..., min_length=1, max_length=253)
    http_port: int = Field(..., ge=1, le=65535)
    ws_port: int = Field(..., ge=1, le=65535)
    use_tls: bool = True
    endpoint_name: str | None = Field(default=None, min_length=1, max_length=64)
    display_name: str | None = Field(default=None, min_length=1, max_length=80)


class SupervisorBluetoothProvisionWifiRequest(SupervisorBluetoothLeaseRequest):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"] = BLE_PROVISIONING_CONTRACT_VERSION
    schema_version: Literal["1.0"] = BLE_PROVISIONING_ENVELOPE_SCHEMA_VERSION
    onboarding_session_id: str = Field(..., min_length=1)
    target_node_id: str = Field(..., min_length=1)
    node_profile_id: Literal["voice"] = "voice"
    payload_schema_id: Literal["hexe.voice_node.wifi_backend.v1"] = VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID
    endpoint_ephemeral_public_key: str = Field(..., min_length=43, max_length=128)
    pairing_nonce: str | None = Field(default=None, min_length=8, max_length=128)
    claim_code_ref: str | None = Field(default=None, min_length=1, max_length=128)
    sequence: int = Field(default=1, ge=1)
    expires_at: str | None = None
    target_address: str | None = Field(default=None, min_length=1, max_length=64)
    credential_payload: SupervisorVoiceWifiProvisioningPayload
    timeout_s: int = Field(default=30, ge=1, le=120)

    @model_validator(mode="after")
    def _validate_pairing_binding(self):
        if not (self.pairing_nonce or self.claim_code_ref):
            raise ValueError("pairing_nonce_or_claim_code_ref_required")
        return self


class ManagedNodeSummary(BaseModel):
    node_id: str
    runtime_kind: str = "standalone_addon"
    lifecycle_state: str = "unknown"
    desired_state: str
    runtime_state: str
    health_status: str
    active_version: str | None = None
    running: bool | None = None
    last_action: str | None = None
    last_action_at: str | None = None


class SupervisorRegisteredRuntimeSummary(BaseModel):
    node_id: str
    node_name: str
    node_type: str
    runtime_kind: str = "real_node"
    desired_state: str
    runtime_state: str
    lifecycle_state: str
    health_status: str
    freshness_state: str = "unknown"
    host_id: str | None = None
    hostname: str | None = None
    api_base_url: str | None = None
    ui_base_url: str | None = None
    health_detail: str | None = None
    registered_at: str | None = None
    updated_at: str | None = None
    last_seen_at: str | None = None
    last_action: str | None = None
    last_action_at: str | None = None
    last_error: str | None = None
    running: bool | None = None
    resource_usage: dict[str, object] = Field(default_factory=dict)
    runtime_metadata: dict[str, object] = Field(default_factory=dict)


class SupervisorNodeServiceSummary(BaseModel):
    service_id: str
    service_state: str
    service_name: str | None = None
    desired_state: str | None = None
    health_status: str | None = None
    updated_at: str | None = None
    pid: int | None = Field(default=None, ge=0)
    container_name: str | None = None
    container_id: str | None = None
    cpu_percent: float | None = Field(default=None)
    mem_percent: float | None = Field(default=None)
    rss_bytes: int | None = Field(default=None, ge=0)
    resource_source: str | None = None
    sampled_at: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SupervisorNodeServicesSummary(BaseModel):
    node_id: str
    api_base_url: str | None = None
    services: list[SupervisorNodeServiceSummary] = Field(default_factory=list)


class SupervisorNodeServiceActionResult(BaseModel):
    action: str
    node_id: str
    service_id: str
    result: dict[str, object] = Field(default_factory=dict)


class SupervisorRuntimeRegistrationRequest(BaseModel):
    node_id: str
    node_name: str
    node_type: str
    host_id: str | None = None
    hostname: str | None = None
    api_base_url: str | None = None
    ui_base_url: str | None = None
    desired_state: str = "running"
    runtime_state: str = "running"
    lifecycle_state: str = "running"
    health_status: str = "unknown"
    health_detail: str | None = None
    last_error: str | None = None
    running: bool | None = True
    resource_usage: dict[str, object] = Field(default_factory=dict)
    runtime_metadata: dict[str, object] = Field(default_factory=dict)


class SupervisorRuntimeHeartbeatRequest(BaseModel):
    node_id: str
    host_id: str | None = None
    hostname: str | None = None
    api_base_url: str | None = None
    ui_base_url: str | None = None
    runtime_state: str | None = None
    lifecycle_state: str | None = None
    health_status: str | None = None
    health_detail: str | None = None
    last_error: str | None = None
    running: bool | None = None
    resource_usage: dict[str, object] = Field(default_factory=dict)
    runtime_metadata: dict[str, object] = Field(default_factory=dict)


class SupervisorRuntimeActionResult(BaseModel):
    action: str
    runtime: SupervisorRegisteredRuntimeSummary


class SupervisorCoreRuntimeSummary(BaseModel):
    runtime_id: str
    runtime_name: str
    runtime_kind: str = "core_service"
    management_mode: str = "monitor"
    desired_state: str
    runtime_state: str
    lifecycle_state: str
    health_status: str
    freshness_state: str = "unknown"
    host_id: str | None = None
    hostname: str | None = None
    registered_at: str | None = None
    updated_at: str | None = None
    last_seen_at: str | None = None
    last_action: str | None = None
    last_action_at: str | None = None
    last_error: str | None = None
    running: bool | None = None
    resource_usage: dict[str, object] = Field(default_factory=dict)
    runtime_metadata: dict[str, object] = Field(default_factory=dict)


class SupervisorCoreRuntimeRegistrationRequest(BaseModel):
    runtime_id: str
    runtime_name: str
    runtime_kind: str = "core_service"
    management_mode: str = "monitor"
    host_id: str | None = None
    hostname: str | None = None
    desired_state: str = "running"
    runtime_state: str = "running"
    lifecycle_state: str = "running"
    health_status: str = "unknown"
    last_error: str | None = None
    running: bool | None = True
    resource_usage: dict[str, object] = Field(default_factory=dict)
    runtime_metadata: dict[str, object] = Field(default_factory=dict)


class SupervisorCoreRuntimeHeartbeatRequest(BaseModel):
    runtime_id: str
    host_id: str | None = None
    hostname: str | None = None
    runtime_state: str | None = None
    lifecycle_state: str | None = None
    health_status: str | None = None
    last_error: str | None = None
    running: bool | None = None
    resource_usage: dict[str, object] = Field(default_factory=dict)
    runtime_metadata: dict[str, object] = Field(default_factory=dict)


class SupervisorCoreRuntimeActionResult(BaseModel):
    action: str
    runtime: SupervisorCoreRuntimeSummary


class SupervisorUpdateStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_mode: Literal["git", "core_host"] = "git"
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    service_update: bool = False
    package_id: str | None = Field(default=None, min_length=1, max_length=128)
    package_manifest: dict[str, object] | None = None
    package_archive_base64: str | None = Field(default=None, min_length=1)
    package_archive_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    package_archive_size: int | None = Field(default=None, ge=1)


class SupervisorUpdateStatusSummary(BaseModel):
    supervisor_id: str
    reported_version: str | None = None
    install_root: str
    source_path: str
    source_is_git_checkout: bool
    supported_modes: list[str] = Field(default_factory=list)
    unsupported_reasons: dict[str, str] = Field(default_factory=dict)
    git: dict[str, object] = Field(default_factory=dict)
    updater: dict[str, object] = Field(default_factory=dict)
    package: dict[str, object] = Field(default_factory=dict)
    update_state: str = "idle"
    current_update: dict[str, object] | None = None
    last_update: dict[str, object] | None = None
    updated_at: str


class SupervisorUpdateStartResult(BaseModel):
    accepted: bool
    state: str
    source_mode: Literal["git", "core_host"]
    idempotency_key: str
    message: str | None = None
    error: str | None = None
    status: SupervisorUpdateStatusSummary


class ProcessResourceSummary(BaseModel):
    rss_bytes: int | None = Field(default=None, ge=0)
    cpu_percent: float | None = Field(default=None)
    open_fds: int | None = Field(default=None, ge=0)
    threads: int | None = Field(default=None, ge=0)


class SupervisorOwnershipBoundary(BaseModel):
    owns: list[str] = Field(default_factory=list)
    depends_on_core_for: list[str] = Field(default_factory=list)


class SupervisorHealthSummary(BaseModel):
    status: str
    host: HostIdentitySummary
    resources: HostResourceSummary
    managed_node_count: int = Field(ge=0)
    healthy_node_count: int = Field(ge=0)
    unhealthy_node_count: int = Field(ge=0)


class SupervisorInfoSummary(BaseModel):
    supervisor_id: str
    host: HostIdentitySummary
    resources: HostResourceSummary
    boundaries: SupervisorOwnershipBoundary
    managed_node_count: int = Field(ge=0)
    managed_nodes: list[ManagedNodeSummary] = Field(default_factory=list)


class SupervisorRuntimeSummary(BaseModel):
    host: HostIdentitySummary
    resources: HostResourceSummary
    process: ProcessResourceSummary
    managed_node_count: int = Field(ge=0)
    managed_nodes: list[ManagedNodeSummary] = Field(default_factory=list)


class SupervisorAdmissionContextSummary(BaseModel):
    admission_state: str = "unknown"
    execution_host_ready: bool = False
    unavailable_reason: str | None = None
    host_busy_rating: int = Field(ge=0, le=10)
    total_capacity_units: int = Field(ge=0)
    available_capacity_units: int = Field(ge=0)
    managed_node_count: int = Field(ge=0)
    healthy_managed_node_count: int = Field(ge=0)


class SupervisorNodeActionResult(BaseModel):
    action: str
    node: ManagedNodeSummary
