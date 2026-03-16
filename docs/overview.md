# Synthia Platform Overview

Synthia is a modular automation and AI platform for home and edge environments. In the current repository, the platform is moving toward a `Core -> Supervisor -> Nodes` structure that makes control-plane, host-runtime, and external-execution boundaries explicit.

## Domain Model

### Core

Status: Implemented

Core is the control plane. It currently owns:

- API hosting
- operator UI hosting
- embedded addon lifecycle authority
- scheduler orchestration
- MQTT authority and messaging policy
- trusted-node trust, governance, and telemetry authority

### Supervisor

Status: Implemented

Supervisor is the host-local runtime authority. In current code this spans:

- `backend/synthia_supervisor/`
- `backend/app/system/runtime/`
- `backend/app/supervisor/`

Current top-level routes:

- `GET /api/supervisor/health`
- `GET /api/supervisor/info`

Broader host-local lifecycle ownership remains Partially implemented.

### Nodes

Status: Implemented

Nodes are trusted external systems that connect to Core. Current implemented flows include onboarding, registration, trust activation, capability declaration, governance issuance, and telemetry reporting.

Current top-level routes:

- `GET /api/nodes`
- `GET /api/nodes/{node_id}`

## Current Platform Shape

```text
Operator UI
  |
Core
  |- API, scheduler, MQTT, addons, trust, governance
  |- Supervisor handoff and runtime visibility
  \- Node orchestration authority

Supervisor
  \- host-local standalone runtime realization

Nodes
  \- trusted external capability providers and execution systems
```

## Extension Boundary

- Embedded addons remain inside Core.
- Supervisor realizes host-local runtime state for standalone compatibility paths.
- Nodes are the canonical external extension and execution model.
- MQTT remains Core-owned and participates in cross-domain coordination where implemented.

## Related Docs

- [core/README.md](./core/README.md)
- [supervisor/README.md](./supervisor/README.md)
- [nodes/README.md](./nodes/README.md)
- [architecture.md](./architecture.md)
