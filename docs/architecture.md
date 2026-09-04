# Hexe Core Architecture

This document describes the current repository architecture as implemented in code. The migration foundation now treats `Core`, `Supervisor`, and `Nodes` as first-class domains without removing the existing subsystem layouts.

Compatibility note: public display names and active MQTT topic roots now use Hexe naming. Some route paths, package/module identifiers, env vars, and service unit filenames still retain legacy forms where compatibility or operational stability matters.

## Domain Boundaries

### Core

Status: Implemented

Core is assembled in `core/backend/app/main.py` and currently spans:

- `core/backend/app/core/`
- `core/backend/app/api/`
- `core/backend/app/system/`
- `frontend/`

Current Core responsibilities include:

- API hosting
- UI hosting
- embedded addon lifecycle authority
- internal recurring Core maintenance tasks
- MQTT authority and runtime coordination
- trusted-node trust and governance authority

### Supervisor

Status: Implemented

Supervisor is the host-local runtime realization boundary and currently spans:

- `core/backend/hexe_supervisor/`
- `core/backend/app/system/runtime/`
- `core/backend/app/supervisor/`
- `supervisor/backend/app/supervisor/`

Standalone Supervisor API routes are served by
`core/backend/app/supervisor/server.py` or the mirrored
`supervisor/backend/app/supervisor/server.py`, not by the Core process.
Current top-level standalone Supervisor routes include:

- `GET /api/supervisor/health`
- `GET /api/supervisor/info`
- `GET /api/supervisor/admission`

Broader host resource and lifecycle ownership remains Partially implemented.

### Nodes

Status: Implemented

Nodes are trusted external systems that connect to Core. Current node code boundaries are:

- `backend/app/system/onboarding/`
- `backend/app/nodes/`

Current top-level routes:

- `GET /api/nodes`
- `GET /api/nodes/{node_id}`

These routes reuse the existing canonical node registration payload shape rather than introducing a second schema.

## Extension Boundary

Status: Implemented

- Embedded addons remain inside Core and are the active local extension model under `backend/app/addons/`.
- Supervisor owns host-local runtime realization and compatibility-era standalone runtime state, but that host-local path is not the canonical external extension model.
- Nodes are the canonical external functionality and execution model. New external compute or integration surfaces should be expressed through node onboarding, trust, capability, governance, and telemetry flows.
- Core remains the MQTT authority for messaging policy and node-facing connectivity material.

## Workload Boundary

Status: Implemented

- Core does not own job queueing, job leasing, or worker execution.
- Supervisor is the host-local runtime authority for services Core asks it to realize.
- Nodes are the canonical external execution layer for external compute and integrations.
- Core retains trust, governance, MQTT authority, and operator-facing control-plane APIs.

## Cross-Domain Flow

### Core -> Supervisor

Status: Implemented

Core writes and inspects standalone runtime intent through the current runtime and supervisor code paths. Supervisor realizes host-local standalone workloads outside the main Core process.

### Core -> Nodes

Status: Implemented

Core remains the trust, governance, and operational authority for nodes. Nodes onboard through Core, receive trust and governance material from Core, and report capabilities and telemetry back into Core-owned services.

### Core Internal Subsystems

Status: Implemented

Major active Core subsystems remain:

- addons and store
- internal scheduler for Core-owned recurring maintenance
- MQTT platform services
- auth, users, policy, telemetry, audit, and settings

## Route Ownership

Core's generated OpenAPI snapshot covers Core-mounted routes. Supervisor-local
routes are documented with Supervisor because they are mounted by the standalone
Supervisor API server.

Core-owned routes include:

- `GET /api/architecture`
- `GET /api/system/supervisor/summary`
- `GET /api/system/supervisor/resources/history`
- `GET /api/system/supervisors`
- `GET /api/system/supervisors/{supervisor_id}`
- `GET /api/nodes`
- `GET /api/nodes/{node_id}`

These routes are mounted in `core/backend/app/main.py` and are implemented
through Core domain modules such as:

- `core/backend/app/architecture/`
- `core/backend/app/api/`
- `core/backend/app/system/`
- `core/backend/app/nodes/`

## Related Docs

- [core/README.md](./core/README.md)
- [supervisor/README.md](./supervisor/README.md)
- [nodes/README.md](./nodes/README.md)
- [overview.md](./overview.md)
