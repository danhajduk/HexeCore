# Node Trust Status Contract

Status: Implemented
Last updated: 2026-03-19

## Purpose

Defines the canonical Core contract for explicit node trust-state inspection after trust activation.

This endpoint exists so a node can distinguish:

- active trust
- explicit Core-side trust revocation
- explicit Core-side node removal

without inferring intent only from generic auth failures.

## Endpoint

- `GET /api/system/nodes/trust-status/{node_id}`

Auth:

- node trust token via `X-Node-Trust-Token`
- or admin session/token

Important behavior:

- this endpoint accepts the last issued node trust token even after Core has revoked or removed the node
- revoked/removed tokens are not accepted for normal trusted-node APIs
- this route is the compatibility-safe exception used for formal revocation/removal signaling

## Response Shape

```json
{
  "ok": true,
  "node_id": "node-abc123",
  "trust_status": "revoked",
  "supported": false,
  "support_state": "removed",
  "registry_present": false,
  "registry_state": null,
  "revoked_at": "2026-03-19T17:40:00+00:00",
  "revocation_reason": "node_removed_by_admin",
  "revocation_action": "remove",
  "message": "This node was removed by Core and is no longer trusted."
}
```

## Field Meanings

- `trust_status`
  - `trusted`
  - `revoked`
- `supported`
  - `true` only when trust is active
- `support_state`
  - `supported`
  - `revoked`
  - `removed`
- `registry_present`
  - whether a registration record still exists in Core
- `registry_state`
  - current registration trust state when a registration still exists
- `revoked_at`
  - timestamp when Core recorded the trust-loss decision
- `revocation_reason`
  - machine-readable Core reason string
- `revocation_action`
  - `revoke` when trust was revoked but registration remains
  - `remove` when the node was removed and the registration record was deleted
- `message`
  - operator/node-readable explanation of the current trust decision

## Node Lifecycle Actions

### Revoke Trust

Route:

- `POST /api/system/nodes/registrations/{node_id}/revoke`

Behavior:

- registration trust state becomes `revoked`
- trust record is retained in revoked form for explicit node-side status reads
- MQTT principal is deprovisioned
- normal trusted-node APIs reject the node token after revocation

### Remove Node

Route:

- `DELETE /api/system/nodes/registrations/{node_id}`

Behavior:

- registration record is deleted
- trust record is retained in revoked form with `revocation_action=remove`
- MQTT principal is deprovisioned
- normal trusted-node APIs reject the node token after removal
- `GET /api/system/nodes/trust-status/{node_id}` remains available to communicate the explicit Core decision

## Node Guidance

When the node receives:

- `supported=true`
  - continue normal trusted operation
- `support_state=revoked`
  - stop trusted operation and surface trust revoked by Core
- `support_state=removed`
  - stop trusted operation and surface node removed by Core

Nodes should treat revocation/removal as a terminal trust state until re-onboarded.

## See Also

- [Node Onboarding API Contract](./node-onboarding-api-contract.md)
- [Node Onboarding Phase 1 Contract](./node-onboarding-phase1-contract.md)
- [Node Trust Activation Payload Contract](./node-trust-activation-payload-contract.md)
