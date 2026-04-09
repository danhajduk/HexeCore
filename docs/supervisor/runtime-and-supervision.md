# Runtime and Supervision

## Current Responsibilities

Status: Implemented

- Core owns desired-state intent and calls into Supervisor for host-local standalone runtime actions where implemented.
- Supervisor reports host resources and process state through `/api/supervisor/health`, `/api/supervisor/resources`, and `/api/supervisor/runtime`.
- Supervisor produces admission context through `/api/supervisor/admission`.
- Supervisor lists standalone addon runtime state and performs start/stop/restart actions through `/api/supervisor/nodes` and the corresponding node action routes.
- Supervisor exposes runtime state and runtime-apply actions for Supervisor-managed helper runtimes (currently `cloudflared`) through:
  - `GET /api/supervisor/runtime/{runtime_id}`
  - `POST /api/supervisor/runtime/{runtime_id}/apply`
- Supervisor now also owns a separate runtime contract for real Nodes through:
  - `POST /api/supervisor/runtimes/register`
  - `POST /api/supervisor/runtimes/heartbeat`
  - `GET /api/supervisor/runtimes`
  - `GET /api/supervisor/runtimes/{node_id}`
  - `POST /api/supervisor/runtimes/{node_id}/start`
  - `POST /api/supervisor/runtimes/{node_id}/stop`
  - `POST /api/supervisor/runtimes/{node_id}/restart`
- Supervisor can proxy node service status and lifecycle actions to the node runtime when node API access is available:
  - `GET /api/supervisor/runtimes/{node_id}/services/status`
  - `POST /api/supervisor/runtimes/{node_id}/services/{service_id}/start`
  - `POST /api/supervisor/runtimes/{node_id}/services/{service_id}/stop`
  - `POST /api/supervisor/runtimes/{node_id}/services/{service_id}/restart`
- Supervisor owns a Core-hosted runtime contract for Core services, addons, and aux containers through:
  - `POST /api/supervisor/core/runtimes/register`
  - `POST /api/supervisor/core/runtimes/heartbeat`
  - `GET /api/supervisor/core/runtimes`
  - `GET /api/supervisor/core/runtimes/{runtime_id}`
  - `POST /api/supervisor/core/runtimes/{runtime_id}/start`
  - `POST /api/supervisor/core/runtimes/{runtime_id}/stop`
  - `POST /api/supervisor/core/runtimes/{runtime_id}/restart`
- Supervisor computes heartbeat freshness for real Nodes as `online`, `stale`, `offline`, or `error` based on the locally tracked runtime record.
- Standalone addon realization is compose-based today through `compose_up` and `compose_down` in `backend/app/supervisor/service.py`.
- Supervisor API service probes are available at `/health` and `/ready` on the standalone Supervisor API server.
- Supervisor exposes boot loop status and manual trigger endpoints:
  - `GET /api/supervisor/boot/status`
  - `POST /api/supervisor/boot/run`

## Aux Container Heartbeats

Status: Implemented

- Core-hosted services and aux containers must send heartbeats to the local Supervisor over the Unix socket at `/run/hexe/supervisor.sock`.
- Heartbeats for Core-owned runtimes are sent via `POST /api/supervisor/core/runtimes/heartbeat` and should include runtime metadata relevant to the aux service.
- Core services are monitor-only and will be rejected when start/stop/restart actions are attempted.
- Core-owned addons and aux services/containers are declared as `manage` to allow Supervisor action intent tracking.
- Each aux container must include a lightweight heartbeat script or sidecar that posts to the Supervisor socket.

## Restart Semantics Boundary

Status: Implemented

- Backend process supervision is owned by systemd user service template (`systemd/user/hexe-backend.service.in`) with:
  - `Restart=always`
  - `RestartSec=2`
- Embedded MQTT docker runtime restart policy is owned by runtime boundary config (`backend/app/system/mqtt/runtime_boundary.py`) via:
  - `SYNTHIA_MQTT_DOCKER_RESTART_POLICY` (default `no`)
- Managed aux containers such as `cloudflared` should use Docker restart policy `no` so Supervisor is the single lifecycle authority.
- This means backend process auto-restart and MQTT container auto-restart are separate controls.
- Operators should not assume backend restart policy implies docker container restart policy.

## Boot Loop Contract

Status: Planned

Supervisor will own a host-local boot loop that turns the boot-order policy into concrete runtime actions.

Inputs:
- Base boot-order JSON: `backend/var/supervisor/boot-order.json`.
- User override YAML: `backend/var/supervisor/boot-order.override.yaml`.
- Core runtime registrations (services/addons/aux containers) via `/api/supervisor/core/runtimes/*`.
- Node runtime registrations via `/api/supervisor/runtimes/*`.

Boot-order merge:
- Supervisor loads the JSON plan first, then applies the YAML override.
- Override changes are additive and may reorder, disable, or adjust dependencies.
- Invalid entries are skipped with a boot log entry and a supervisor warning.

Dependency resolution:
- Core services and Core-owned runtimes are evaluated first (if present on the host).
- Aux runtimes (addons/aux containers) are gated by core readiness where required.
- Nodes are evaluated after Core runtimes and in dependency order.
- Node dependencies can include other node types (ex: email depends on ai-node) and aux runtimes (ex: mqtt).

Readiness gates:
- Each runtime action waits for a health signal before the next dependency starts.
- Health sources include heartbeat freshness, runtime state, and explicit health status when available.
- Timeouts are enforced per runtime; on timeout the runtime is marked unhealthy and the boot loop continues.

Outputs:
- A boot loop status summary for the active host.
- Boot log entries for each step (start/stop/restart + readiness result).

## Store and Runtime Interaction

Status: Implemented

- Store lifecycle writes desired/runtime-linked state for addon deployment outcomes.
- Runtime status and diagnostics APIs expose deployment/runtime realization status.
- Core Node registry views can now consume Supervisor-owned runtime truth for real Nodes in read-only form without moving governance ownership out of Core.

## Explicit Non-Goals

Status: Implemented

Supervisor does not currently implement:

- OS administration
- package management
- general service supervision outside Hexe-managed runtimes
- firewall or network policy control
- non-Hexe orchestration
- arbitrary third-party container lifecycle control outside explicit Hexe-managed runtimes

## Future Expansion Path

Status: Not developed

Future growth can extend this boundary toward:

- broader host-local workload supervision
- managed worker execution ownership
- richer reconciliation loops
- runtime backends beyond compose

## See Also

- [../architecture.md](../architecture.md)
- [Operators Guide](../operators-guide.md)
- [../core/README.md](../core/README.md)
