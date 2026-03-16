# Synthia Core Architecture

This document describes the current repository architecture as implemented in code. The migration foundation now treats `Core`, `Supervisor`, and `Nodes` as first-class domains without removing the existing subsystem layouts.

## Domain Boundaries

### Core

Status: Implemented

Core is assembled in `backend/app/main.py` and currently spans:

- `backend/app/core/`
- `backend/app/api/`
- `backend/app/system/`
- `frontend/`

Current Core responsibilities include:

- API hosting
- UI hosting
- addon lifecycle authority
- scheduler orchestration
- MQTT authority and runtime coordination
- trusted-node trust and governance authority

### Supervisor

Status: Implemented

Supervisor is the host-local runtime realization boundary and currently spans:

- `backend/synthia_supervisor/`
- `backend/app/system/runtime/`
- `backend/app/supervisor/`

Current top-level routes:

- `GET /api/supervisor/health`
- `GET /api/supervisor/info`

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
- scheduler and workers
- MQTT platform services
- auth, users, policy, telemetry, audit, and settings

## Foundation Route Map

The migration foundation currently adds:

- `GET /api/architecture`
- `GET /api/supervisor/health`
- `GET /api/supervisor/info`
- `GET /api/nodes`
- `GET /api/nodes/{node_id}`

These routes are mounted in `backend/app/main.py` and are implemented through the new wrappers in:

- `backend/app/architecture/`
- `backend/app/supervisor/`
- `backend/app/nodes/`

## Related Docs

- [core/README.md](./core/README.md)
- [supervisor/README.md](./supervisor/README.md)
- [nodes/README.md](./nodes/README.md)
- [overview.md](./overview.md)
