# Core Docs

This is the canonical entrypoint for Core documentation in the `Core -> Supervisor -> Nodes` structure.

## Status

Status: Implemented

Core is currently implemented across:

- `backend/app/main.py`
- `backend/app/core/`
- `backend/app/api/`
- `backend/app/system/`
- `frontend/`

## Core Responsibilities

- API hosting
- operator UI hosting
- addon lifecycle authority
- scheduler orchestration
- MQTT authority and messaging policy
- trusted-node trust, governance, and telemetry authority

## Current Core Documentation Map

- [./api/README.md](./api/README.md)
- [./frontend/README.md](./frontend/README.md)
- [./scheduler/README.md](./scheduler/README.md)
- [../workers/README.md](../workers/README.md)
- [../addons/README.md](../addons/README.md)
- [../mqtt/README.md](../mqtt/README.md)

## Migration Structure

The folders `docs/core/api/`, `docs/core/frontend/`, and `docs/core/scheduler/` now hold the re-homed Core API, frontend, and scheduler docs.
