# Nodes Docs

This is the canonical entrypoint for Nodes documentation in the `Core -> Supervisor -> Nodes` structure.

## Status

Status: Implemented

Current node code boundaries:

- `backend/app/system/onboarding/`
- `backend/app/nodes/`

## Current Responsibilities

- onboarding sessions and approval flow
- registration and trust activation
- capability declaration and profile acceptance
- governance issuance and refresh
- telemetry ingestion and operational status projection
- migration-foundation route exposure through:
  - `GET /api/nodes`
  - `GET /api/nodes/{node_id}`

The new top-level node routes reuse the existing canonical registration payload shape.

## Included Docs

- [registry-domain.md](./registry-domain.md)
- [node-onboarding-registration-architecture.md](./node-onboarding-registration-architecture.md)
- [node-onboarding-api-contract.md](./node-onboarding-api-contract.md)
- [node-phase2-lifecycle-contract.md](./node-phase2-lifecycle-contract.md)
- [node-lifecycle.md](./node-lifecycle.md)

## See Also

- [../architecture.md](../architecture.md)
- [../fastapi/api-reference.md](../fastapi/api-reference.md)
- [../mqtt/mqtt-platform.md](../mqtt/mqtt-platform.md)
- [../temp-ai-node/README.md](../temp-ai-node/README.md)
