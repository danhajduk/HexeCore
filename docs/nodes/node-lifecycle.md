# Node Lifecycle

This document describes the trusted-node lifecycle as verified in the current repository.

Primary code:
- `backend/app/system/onboarding/sessions.py`
- `backend/app/system/onboarding/registrations.py`
- `backend/app/system/onboarding/governance.py`

## Onboarding Session Lifecycle

Status: Implemented

Node onboarding sessions move through these verified states:

- `pending`
- `approved`
- `rejected`
- `expired`
- `consumed`
- `cancelled`

Current allowed transitions in code:

- `pending` -> `approved`
- `pending` -> `rejected`
- `pending` -> `expired`
- `pending` -> `cancelled`
- `approved` -> `consumed`

Each session records state-history entries with timestamps, previous state, next state, actor identity, and reason.

## Registration Lifecycle

Status: Implemented

- Approved onboarding sessions can be converted into node registration records.
- Registrations are stored with node identity, trust status, capability summary, approval metadata, and lifecycle timestamps.
- Trust status values accepted by the registration store are `pending`, `approved`, `trusted`, `revoked`, and `rejected`.

## Governance Lifecycle

Status: Implemented

- Governance bundles are issued per node and capability profile.
- Each bundle records `node_id`, `capability_profile_id`, `governance_version`, and `issued_timestamp`.
- Baseline issuance increments versions using the `gov-vN` pattern when a new revision is created.

## Operational Lifecycle

Status: Partially implemented

- The repository includes onboarding, registration, capability declaration, governance, and telemetry flows.
- The broader node operational model is documented across the existing node contract docs rather than one single lifecycle service file.

Phase-oriented lifecycle states documented across the current node contracts:

- Phase 1 onboarding path:
  - `pending_approval`
  - `trusted`
- Phase 2 readiness path:
  - `capability_setup_pending`
  - `operational`
  - `degraded`

Operational readiness guidance:
- `capability_setup_pending` is a blocked pre-operational state
- transition to `operational` requires accepted capabilities, issued governance, and `operational_ready=true`
- setup and runtime polling use `GET /api/system/nodes/operational-status/{node_id}`

## See Also

- [node-onboarding-registration-architecture.md](./node-onboarding-registration-architecture.md)
- [node-onboarding-api-contract.md](./node-onboarding-api-contract.md)
- [node-phase2-lifecycle-contract.md](./node-phase2-lifecycle-contract.md)
- [../temp-ai-node/README.md](../temp-ai-node/README.md)
