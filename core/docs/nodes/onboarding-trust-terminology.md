# Node Onboarding And Trust Terminology

Status: Implemented

This document defines the canonical terminology for node onboarding, registration, trust activation, and capability activation.

## Canonical Terms

### Onboarding Session

The pre-trust session created by:

- `POST /api/system/nodes/onboarding/sessions`

This is the canonical term for the pending bootstrap flow before a node becomes trusted.

### Approval Decision

The operator-mediated approve or reject action applied to an onboarding session.

Canonical decision routes:

- `GET /api/system/nodes/onboarding/sessions/{session_id}?state=...`
- `POST /api/system/nodes/onboarding/sessions/{session_id}/approve?state=...`
- `POST /api/system/nodes/onboarding/sessions/{session_id}/reject?state=...`

### Registration Record

The persisted node identity record created from approved onboarding and stored in the node registration domain.

Canonical route family:

- `GET /api/system/nodes/registrations`
- `GET /api/system/nodes/registrations/{node_id}`
- `GET /api/nodes`
- `GET /api/nodes/{node_id}`

### Trust Activation

The one-time activation payload returned when an approved onboarding session is finalized successfully.

Canonical finalize route:

- `GET /api/system/nodes/onboarding/sessions/{session_id}/finalize?node_nonce=...`

Trust activation is not the same thing as approval. Approval authorizes the session. Finalization consumes that approval and returns trust material.

### Capability Activation

The post-trust process where a trusted node declares capabilities, receives a capability profile, and becomes governance-ready.

Canonical route family:

- `POST /api/system/nodes/capabilities/declaration`
- `GET /api/system/nodes/capabilities/profiles*`
- `GET /api/system/nodes/governance/current`
- `POST /api/system/nodes/governance/refresh`

## Compatibility Rule

`AI-node` terminology is now profile-specific compatibility language, not the canonical contract name.

Use:

- `node` for the global contract
- `AI-node` only when describing the AI-node profile or legacy compatibility clients
