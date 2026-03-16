# Synthia Core

Synthia Core is the control-plane service for the Synthia platform. This repository now documents the migration foundation for the `Core -> Supervisor -> Nodes` structure while preserving the current runtime and API surface.

## Start Here

- [docs/index.md](docs/index.md)
- [docs/overview.md](docs/overview.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/core/README.md](docs/core/README.md)
- [docs/supervisor/README.md](docs/supervisor/README.md)
- [docs/nodes/README.md](docs/nodes/README.md)
- [docs/mqtt/README.md](docs/mqtt/README.md)

## Domain Summary

### Core

Status: Implemented

Core currently spans:

- `backend/app/main.py`
- `backend/app/core/`
- `backend/app/api/`
- `backend/app/system/`
- `frontend/`

Core owns API hosting, UI hosting, addon lifecycle authority, scheduler orchestration, MQTT authority, and trusted-node governance flows.

### Supervisor

Status: Implemented

Supervisor currently spans:

- `backend/synthia_supervisor/`
- `backend/app/system/runtime/`
- `backend/app/supervisor/`

The migration foundation exposes:

- `GET /api/supervisor/health`
- `GET /api/supervisor/info`

### Nodes

Status: Implemented

Node services currently span:

- `backend/app/system/onboarding/`
- `backend/app/nodes/`

The migration foundation exposes:

- `GET /api/nodes`
- `GET /api/nodes/{node_id}`

These routes reuse the existing canonical node registration payload shape.

## Repository Layout

- `backend/app/`: FastAPI app, Core control-plane services, and migration domain routers
- `backend/synthia_supervisor/`: standalone runtime supervision and desired/runtime reconciliation
- `frontend/`: React operator UI
- `docs/`: canonical repository documentation
- `scripts/`: development and bootstrap helpers
- `systemd/`: service templates and runtime integration

## Local Development

Backend dependencies:

- `backend/requirements.txt`

Frontend dependencies:

- `frontend/package.json`

Typical development flow:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --reload --port 9001
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev -- --port 80
```

## Current Architecture Note

The repository is additive-first during migration. Core, Supervisor, and Nodes are now first-class documentation and API domains, but existing subsystem layouts remain active until later migration tasks re-home or retire them.
