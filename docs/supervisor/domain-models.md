# Supervisor Domain Models

Status: Implemented

This document defines the current Supervisor domain models exposed by the migration foundation in code.

## Source Of Truth

- `backend/app/supervisor/models.py`
- `backend/app/supervisor/service.py`
- `backend/app/supervisor/router.py`
- `backend/app/supervisor/runtime_store.py`

## Models

### HostIdentitySummary

- `host_id`
- `hostname`
- `runtime_provider`
- `managed_runtime_type`

### HostResourceSummary

- `uptime_s`
- `load_1m`
- `load_5m`
- `load_15m`
- `cpu_percent_total`
- `cpu_cores_logical`
- `memory_total_bytes`
- `memory_available_bytes`
- `memory_percent`
- `root_disk_total_bytes`
- `root_disk_free_bytes`
- `root_disk_percent`
- `gpu_count`
- `gpu_utilization_percent`
- `gpu_memory_percent`
- `gpu_devices`
- `cuda_available`
- `cuda_version`
- `bluetooth_present`
- `bluetooth_powered`
- `bluetooth_ensure_powered`
- `bluetooth_power_error`
- `bluetooth_adapters`
- `network_rx_Bps`
- `network_tx_Bps`
- `network_bytes_recv`
- `network_bytes_sent`
- `network_errin`
- `network_errout`
- `network_dropin`
- `network_dropout`
- `network_primary_interface`
- `network_primary_type`
- `network_link_speed_mbps`
- `wifi_signal_percent`
- `internet_reachable`
- `internet_check_error`

Supervisor samples host-local CPU, memory, disk, network, GPU, Bluetooth, and internet reachability fields. Bluetooth fields describe adapter presence and power state only; they do not grant node access to Bluetooth hardware.

### SupervisorBluetoothLeaseRequest

Status: Implemented

Accepted by:

- `POST /api/supervisor/hardware/bluetooth/ble/status`

Fields include:

- `node_id`
- `lease_token`
- `adapter`

The `lease_token` must be a Core-issued hardware lease for the same node, Supervisor, resource, adapter when scoped, and BLE operation.

### SupervisorBluetoothBleScanRequest

Status: Implemented

Accepted by:

- `POST /api/supervisor/hardware/bluetooth/ble/scan`

Fields include:

- `node_id`
- `lease_token`
- `adapter`
- `scan_seconds`

`scan_seconds` is bounded from 1 to 30 seconds. The scan route validates the lease before running a bounded BLE scan through Supervisor-managed `bluetoothctl`.

### SupervisorBluetoothProvisionWifiRequest

Status: Implemented

Accepted by:

- `POST /api/supervisor/hardware/bluetooth/ble/provision-wifi`

Fields include:

- `node_id`
- `lease_token`
- `adapter`
- `contract_version`
- `onboarding_session_id`
- `target_node_id`
- `node_profile_id`
- `payload_schema_id`
- `pairing_nonce`
- `claim_code_ref`
- `target_address`
- `credential_payload`
- `timeout_s`

The route validates a Core-issued `hardware.bluetooth.ble.provision_wifi` lease, enforces the Voice node Wi-Fi/backend payload schema, redacts `wifi_password` from responses, and delegates the actual GATT write to the configured Supervisor BLE provisioning backend. Without a backend, it fails closed with `gatt_backend_unavailable`.

### ManagedNodeSummary

- `node_id`
- `runtime_kind`
- `desired_state`
- `runtime_state`
- `health_status`
- `active_version`
- `running`

Current implementation maps host-local standalone addon runtimes into the Supervisor-managed node summary model.

### SupervisorRegisteredRuntimeSummary

Status: Implemented

This model represents a real Supervisor-managed Node runtime and is separate from the compatibility-era standalone addon runtime summary model.

Returned by:

- `POST /api/supervisor/runtimes/register`
- `POST /api/supervisor/runtimes/heartbeat`
- `GET /api/supervisor/runtimes/{node_id}`

Included in:

- `GET /api/supervisor/runtimes`

Fields include:

- `node_id`
- `node_name`
- `node_type`
- `runtime_kind`
- `desired_state`
- `runtime_state`
- `lifecycle_state`
- `health_status`
- `freshness_state`
- `host_id`
- `hostname`
- `api_base_url`
- `ui_base_url`
- `health_detail`
- `registered_at`
- `updated_at`
- `last_seen_at`
- `last_action`
- `last_action_at`
- `last_error`
- `running`
- `resource_usage`
- `runtime_metadata`

Resource observation:

- `resource_usage` may be enriched by Supervisor from host-local metadata before the summary is returned.
- `runtime_metadata.services[]` or `runtime_metadata.services.{id}` entries are sampled when they include `pid`, `systemd_unit`, `systemd_service`, `container_name`, or `container_id`.
- Supervisor-derived fields include `pid`, `cpu_percent`, `mem_percent`, `rss_bytes`, `container_name`, `container_id`, `resource_source`, and `sampled_at`.
- Reported service telemetry fields such as `rps`, `latency_ms_avg`, `latency_ms_p95`, `error_rate`, and `inflight` are preserved in resource history samples when present.
- When Supervisor can sample a local process or container, sampled CPU and memory are treated as authoritative over heartbeat-provided CPU and memory.

### SupervisorRuntimeRegistrationRequest

Status: Implemented

Accepted by:

- `POST /api/supervisor/runtimes/register`

Purpose:

- register or refresh a real Node runtime with the local Supervisor
- establish the Supervisor-owned runtime identity and local state view

### SupervisorRuntimeHeartbeatRequest

Status: Implemented

Accepted by:

- `POST /api/supervisor/runtimes/heartbeat`

Purpose:

- refresh runtime liveness
- update runtime state, health, and resource usage
- keep heartbeat freshness under Supervisor ownership

### SupervisorRuntimeActionResult

Status: Implemented

Returned by:

- `POST /api/supervisor/runtimes/{node_id}/start`
- `POST /api/supervisor/runtimes/{node_id}/stop`
- `POST /api/supervisor/runtimes/{node_id}/restart`
- `GET /api/supervisor/runtimes/{node_id}/services/status`
- `POST /api/supervisor/runtimes/{node_id}/services/{service_id}/start`
- `POST /api/supervisor/runtimes/{node_id}/services/{service_id}/stop`
- `POST /api/supervisor/runtimes/{node_id}/services/{service_id}/restart`
- `POST /api/supervisor/core/runtimes/register`
- `POST /api/supervisor/core/runtimes/heartbeat`
- `GET /api/supervisor/core/runtimes`
- `GET /api/supervisor/core/runtimes/{runtime_id}`
- `POST /api/supervisor/core/runtimes/{runtime_id}/start`
- `POST /api/supervisor/core/runtimes/{runtime_id}/stop`
- `POST /api/supervisor/core/runtimes/{runtime_id}/restart`

Includes:

- `action`
- `runtime`

### SupervisorCoreRuntimeSummary

Status: Implemented

This model represents Core-hosted runtimes (core services, addons, aux services/containers) declared to the local Supervisor.

Returned by:

- `POST /api/supervisor/core/runtimes/register`
- `POST /api/supervisor/core/runtimes/heartbeat`
- `GET /api/supervisor/core/runtimes/{runtime_id}`

Included in:

- `GET /api/supervisor/core/runtimes`

Fields include:

- `runtime_id`
- `runtime_name`
- `runtime_kind`
- `management_mode`
- `desired_state`
- `runtime_state`
- `lifecycle_state`
- `health_status`
- `freshness_state`
- `host_id`
- `hostname`
- `registered_at`
- `updated_at`
- `last_seen_at`
- `last_action`
- `last_action_at`
- `last_error`
- `running`
- `resource_usage`
- `runtime_metadata`

Resource observation:

- Core runtime summaries use the same Supervisor-local resource enrichment as Node runtime summaries.
- Core services commonly use `runtime_metadata.systemd_unit`; aux containers and addons commonly use `runtime_metadata.container_name`, `runtime_metadata.container_id`, or `runtime_metadata.containers[]`.
- `runtime_metadata.services` can also be used when one runtime exposes multiple local process/container children.
- Local Core fleet sync enriches the `core-api` runtime `resource_usage` with the current Core API metrics snapshot (`rps`, `latency_ms_p95`, `error_rate`, and related counters) before persisting the Supervisor Fleet heartbeat.

### SupervisorCoreRuntimeRegistrationRequest

Status: Implemented

Accepted by:

- `POST /api/supervisor/core/runtimes/register`

Purpose:

- declare a Core-hosted runtime to the local Supervisor
- define if the runtime is monitor-only (`core_service`) or manageable (`addon`, `aux_service`, `aux_container`)

### SupervisorCoreRuntimeHeartbeatRequest

Status: Implemented

Accepted by:

- `POST /api/supervisor/core/runtimes/heartbeat`

Purpose:

- refresh Core-hosted runtime liveness
- update runtime state, health, and resource usage
- keep heartbeat freshness under Supervisor ownership

### SupervisorCoreRuntimeActionResult

Status: Implemented

Returned by:

- `POST /api/supervisor/core/runtimes/{runtime_id}/start`
- `POST /api/supervisor/core/runtimes/{runtime_id}/stop`
- `POST /api/supervisor/core/runtimes/{runtime_id}/restart`

Includes:

- `action`
- `runtime`

## Compatibility Service Boundary

Status: Implemented

The Supervisor domain service now also acts as the compatibility boundary for host-local collection that still feeds Core-owned routes.

Current compatibility methods:

- `system_stats()`
- `system_snapshot()`
- `process_stats()`

Current compatibility consumers:

- `backend/app/system/stats/router.py`
- `backend/app/system/sampler.py`

This keeps existing Core routes stable while shifting host-local inspection behind the Supervisor service layer.

### SupervisorHealthSummary

Returned by:

- `GET /api/supervisor/health`

Includes:

- `status`
- `host`
- `resources`
- `managed_node_count`
- `healthy_node_count`
- `unhealthy_node_count`

### SupervisorInfoSummary

Returned by:

- `GET /api/supervisor/info`

Includes:

- `supervisor_id`
- `host`
- `resources`
- `boundaries`
- `managed_node_count`
- `managed_nodes`

### SupervisorRuntimeSummary

Returned by:

- `GET /api/supervisor/runtime`

Includes:

- `host`
- `resources`
- `process`
- `managed_node_count`
- `managed_nodes`

### SupervisorAdmissionContextSummary

Returned by:

- `GET /api/supervisor/admission`

Includes:

- `admission_state`
- `execution_host_ready`
- `unavailable_reason`
- `host_busy_rating`
- `total_capacity_units`
- `available_capacity_units`
- `managed_node_count`
- `healthy_managed_node_count`

### SupervisorRuntimeState (Cloudflared)

Status: Implemented

Returned by:

- `GET /api/supervisor/runtime/{runtime_id}`

Notes:

- `runtime_id=cloudflared` returns a runtime state payload with `exists=true`.
- Docker-backed `cloudflared` state is enriched from the configured container identity when Docker stats are available.
- Binary-backed `cloudflared` state is enriched from the stored pid file when the process is still visible to the Supervisor host.
- Other runtime ids currently return `{ "exists": false }`.

### SupervisorRuntimeApplyResult (Cloudflared)

Status: Implemented

Returned by:

- `POST /api/supervisor/runtime/{runtime_id}/apply`

Notes:

- `runtime_id=cloudflared` applies the rendered tunnel configuration and returns `ok`, `runtime_state`, and `config_path`.
- Unsupported runtime ids return `{ "ok": false, "runtime_state": "unsupported" }`.

### Supervisor Host API Surface

Status: Implemented

Current Supervisor routes:

- `GET /api/supervisor/health`
- `GET /api/supervisor/info`
- `GET /api/supervisor/resources`
- `GET /api/supervisor/runtime`
- `GET /api/supervisor/runtime/{runtime_id}`
- `POST /api/supervisor/runtime/{runtime_id}/apply`
- `GET /api/supervisor/admission`
- `GET /api/supervisor/nodes`
- `POST /api/supervisor/nodes/{node_id}/start`
- `POST /api/supervisor/nodes/{node_id}/stop`
- `POST /api/supervisor/nodes/{node_id}/restart`
- `POST /api/supervisor/runtimes/register`
- `POST /api/supervisor/runtimes/heartbeat`
- `GET /api/supervisor/runtimes`
- `GET /api/supervisor/runtimes/{node_id}`
- `POST /api/supervisor/runtimes/{node_id}/start`
- `POST /api/supervisor/runtimes/{node_id}/stop`
- `POST /api/supervisor/runtimes/{node_id}/restart`

Supervisor service probes:

- `GET /health`
- `GET /ready`

Schemas:

- [../json_schema/supervisor.models.schema.json](../json_schema/supervisor.models.schema.json)
- [../json_schema/supervisor.api.schema.json](../json_schema/supervisor.api.schema.json)
- [../json_schema/supervisor.runtime-nodes.schema.json](../json_schema/supervisor.runtime-nodes.schema.json)
- [../json_schema/supervisor.core-runtimes.schema.json](../json_schema/supervisor.core-runtimes.schema.json)

## Ownership Boundary

Current Supervisor ownership:

- host monitoring and runtime resource summaries
- admission context reporting
- host-local standalone runtime realization
- standalone workload lifecycle execution
- real Node runtime registration
- real Node heartbeat freshness tracking
- real Node runtime state projection
- real Node runtime action intent tracking
- Core runtime declaration and heartbeat freshness tracking
- Core runtime action intent tracking for manageable Core-hosted runtimes

Current Core-owned dependencies:

- global governance and scheduler policy
- node trust and onboarding authority
- operator UI and control-plane APIs

Explicit non-goals in the current repository state:

- OS administration
- package management
- general service management outside Hexe-managed runtimes
- firewall and network policy
- non-Hexe orchestration

Future expansion path:

- broader host-local workload supervision
- managed worker execution ownership
- richer reconciliation loops
- runtime backends beyond compose
