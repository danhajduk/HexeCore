# MQTT Broker Runtime Boundary (Embedded)

Last Updated: 2026-03-09 08:26 US/Pacific

## Boundary Definition

Embedded MQTT broker runtime is treated as platform infrastructure and separated from addon registry/proxy flows.

Core-side boundary interface:
- `backend/app/system/mqtt/runtime_boundary.py`
  - `ensure_running`
  - `health_check`
  - `reload`
  - `controlled_restart`
  - `get_status`

## Degraded-State Semantics

Runtime status contract:
- `state` (`running` / `stopped` or provider-specific equivalent)
- `healthy` boolean
- `degraded_reason` optional reason string
- `checked_at` timestamp

## Implementation Note

Current implementation in repo:
- `InMemoryBrokerRuntimeBoundary` provides deterministic behavior for boundary integration/testing.
- `MosquittoProcessRuntimeBoundary` provides Phase 1 process control for an embedded Mosquitto runtime:
  - start (`mosquitto -c <live>/broker.conf`)
  - stop (graceful terminate + forced kill fallback)
  - reload (`SIGHUP`)
  - health checks (process alive + TCP connect probe)
  - connection/runtime status via boundary status object
