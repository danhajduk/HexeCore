# Hexe Core

Hexe Core is the control-plane service for the Hexe AI platform. This repository now documents the migration foundation for the `Core -> Supervisor -> Nodes` structure while preserving the current runtime and API surface.

Compatibility note: Phase 0 is a cosmetic rebrand only. Internal identifiers such as `synthia/...` MQTT topics, `/api/...` paths, Python module names, and systemd unit filenames remain unchanged during this phase.

## Start Here

- [core/docs/index.md](core/docs/index.md)
- [core/docs/overview.md](core/docs/overview.md)
- [core/docs/architecture.md](core/docs/architecture.md)
- [core/docs/core/README.md](core/docs/core/README.md)
- [core/docs/supervisor/README.md](core/docs/supervisor/README.md)
- [core/docs/nodes/README.md](core/docs/nodes/README.md)
- [core/docs/mqtt/README.md](core/docs/mqtt/README.md)

## Domain Summary

### Core

Status: Implemented

Core currently spans:

- `core/backend/app/main.py`
- `core/backend/app/core/`
- `core/backend/app/api/`
- `core/backend/app/system/`
- `core/frontend/`

Hexe Core owns API hosting, UI hosting, embedded addon lifecycle authority, scheduler orchestration and workload admission, MQTT authority, and trusted-node governance flows.

### Supervisor

Status: Implemented

Supervisor currently spans:

- `core/backend/synthia_supervisor/`
- `core/backend/app/system/runtime/`
- `core/backend/app/supervisor/`

Current responsibilities:

- `GET /api/supervisor/health`
- `GET /api/supervisor/info`
- `GET /api/supervisor/resources`
- `GET /api/supervisor/runtime`
- `GET /api/supervisor/admission`
- `GET /api/supervisor/nodes`
- `POST /api/supervisor/nodes/{node_id}/start`
- `POST /api/supervisor/nodes/{node_id}/stop`
- `POST /api/supervisor/nodes/{node_id}/restart`

Current non-goals:

- OS administration
- package management
- general service management outside Hexe-managed runtimes
- firewall/network policy
- non-Hexe orchestration

### Nodes

Status: Implemented

Node services currently span:

- `core/backend/app/system/onboarding/`
- `core/backend/app/nodes/`

The migration foundation exposes:

- `GET /api/nodes`
- `GET /api/nodes/{node_id}`
- `GET /api/nodes/{node_id}/ui-manifest`

These routes reuse the existing canonical node registration payload shape.

## Extension Boundary

- Embedded addons stay inside the Core runtime.
- Supervisor realizes host-local runtime intent and compatibility-era standalone runtime state.
- External functionality is node-first in the migration structure. New external capability providers should be modeled as Nodes, not as standalone addons.
- MQTT remains Core-owned and is used as part of Core-to-node and Core-to-addon coordination where implemented.

## Workload Boundary

- Core scheduler APIs own queueing, admission, and orchestration decisions.
- Execution happens through worker/runtime clients outside that Core admission path where implemented today.
- Supervisor and Nodes are the target runtime boundaries for host-local and external execution respectively.

## Repository Layout

- `core/`: Core control-plane application, operator UI, documentation, scripts, and service templates
- `supervisor/`: Supervisor checkout content preserved as a first-class top-level directory
- `core/backend/app/`: FastAPI app, Core control-plane services, and migration domain routers
- `core/backend/synthia_supervisor/`: standalone runtime supervision and desired/runtime reconciliation
- `core/frontend/`: React operator UI
- `core/docs/`: canonical repository documentation
- `core/docs/standards/Node/tomplate/`: starter modular template for creating a new Hexe node
- `core/scripts/`: development and bootstrap helpers
- `core/systemd/`: service templates and runtime integration

## Local Development

Backend dependencies:

- `core/backend/requirements.txt`

Frontend dependencies:

- `core/frontend/package.json`

Typical development flow:

```bash
cd core/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --reload --port 9001
```

In a second terminal:

```bash
cd core/frontend
npm install
npm run dev -- --port 5173
```

## Current Architecture Note

The repository is additive-first during migration. Core, Supervisor, and Nodes are now first-class documentation and API domains, but existing subsystem layouts remain active until later migration tasks re-home or retire them.
