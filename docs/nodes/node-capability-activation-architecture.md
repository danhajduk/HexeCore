# Node Capability Activation Architecture (Phase 2)

Status: Implemented (Phase 2 baseline)  
Last Updated: 2026-03-19 17:20

## Purpose
Defines the Core-side architecture target for Phase 2 node capability activation after trust activation is complete.

Terminology note:

- `trust activation` is the finalize payload phase
- `capability activation` is the later capability declaration/profile/governance phase

This document is the source of truth for:
- capability declaration intake
- capability profile registration
- baseline governance bundle issuance
- operational-readiness state progression
- canonical capability taxonomy publication

This document does not define prompt/task execution logic.

## Scope Boundary
- In scope: node capability identity and governance baseline flow.
- Out of scope: task routing, policy enforcement engine internals, execution planning.

## Current Implementation State
Implemented:
- Canonical capability declaration schema module and strict validator (`backend/app/system/onboarding/capability_manifest.py`).
- Trusted node capability declaration API and accepted-profile persistence.
- Immutable capability profile registry and admin lookup APIs.
- Governance bundle issuance, distribution, and version-aware refresh APIs.
- Governance version status tracking and operational readiness projection in node registry payloads.
- Node operational status endpoint and node telemetry ingestion endpoint for lifecycle/governance runtime signals.

## Phase 2 Core Components
### AI Node (trusted)
- Submits capability declaration payload after trust activation.
- Requests governance bundle and periodic refresh.
- Reports runtime lifecycle and governance-sync telemetry.

### Core Capability Registry
- Validates and stores accepted capability declarations.
- Produces immutable capability profile records.
- Provides capability inspection for admin and future routing/policy phases.

### Core Governance Service
- Generates baseline governance bundles based on node class and accepted capability profile.
- Versions governance bundles and tracks issuance/refresh.
- Persists per-node governance status metadata (`active_governance_version`, `last_issued_timestamp`, `last_refresh_request_timestamp`).

### Core Node Management Layer
- Owns node lifecycle model and readiness progression.
- Combines trust status, capability acceptance status, and governance sync status.
- Exposes operational state to UI and node-facing status APIs.
- Projects readiness separately from lifecycle labeling where needed during compatibility transitions.

## Phase 2 Responsibilities After Trust Activation
After Phase 1 trust activation, Core must:
1. Receive node capability declarations.
2. Validate declaration payload against canonical manifest schema.
3. Register accepted capability profile tied to `node_id`.
4. Issue baseline governance bundle for that node profile.
5. Track node operational state using lifecycle criteria.

## Interaction Flow (Target)
```mermaid
sequenceDiagram
    participant N as AI Node
    participant C as Core Capability Registry
    participant G as Core Governance Service
    participant M as Core Node Management

    N->>C: POST capability declaration (trusted identity)
    C->>C: validate schema + validate capability values
    C->>C: persist raw declaration + immutable capability profile
    C-->>M: capability_status=accepted + capability_profile_id
    M->>G: request baseline governance for node/profile
    G->>G: generate governance bundle + governance_version
    G-->>M: governance issued metadata
    M-->>N: operational status update (capability/governance)
    N->>G: GET governance bundle / refresh
    N->>M: POST telemetry lifecycle/governance-sync signals
```

## Data Ownership (Target)
- Node identity/trust: existing onboarding + trust domain (`node_id`, trust token, trust status).
- Capability declaration: raw manifest payload tied to node identity.
- Capability profile: normalized immutable record derived from accepted declaration.
- Governance bundle: versioned baseline bundle tied to node + profile.
- Operational state: lifecycle projection owned by node management layer.

## Validation Boundaries (Target)
- Authentication: declaration/governance/status APIs must require trusted node identity.
- Schema strictness: manifest rejects unknown keys and unsupported versions.
- Determinism: capability acceptance logic must not silently rewrite declaration intent.
- Compatibility: schema and governance bundle versions must be explicit and comparable.

## Operational Readiness Criteria (Target)
Node is operational only when all are true:
1. trust status is `trusted`
2. capability declaration is `accepted`
3. governance bundle is issued/synced for active profile

Any missing criterion keeps node non-operational.

Compatibility note:

- In current live behavior, `operational_ready` may already project `true` before all surfaces normalize the lifecycle label to `operational`.
- Documentation and client logic should therefore treat `operational_ready` as the canonical readiness projection and `lifecycle_state` as a related lifecycle label that may lag during compatibility windows.

## Startup Continuation Behavior

Trusted startup is not always a forced stop in setup:

- A trusted node can resume into `capability_setup_pending` as the default post-trust Phase 2 path.
- If accepted capability state and fresh governance are already present for the active node profile, the node may continue through its local fast-path checks and become operational during startup.
- This is valid implemented behavior and should be reflected in review, testing, and operator guidance.

## Node-Local Setup Payload Boundary

Core owns the readiness projection contract exposed by `GET /api/system/nodes/operational-status/{node_id}`.

The AI-node UI also depends on node-local setup payload details that are not modeled as Core-owned fields, including:

- provider selection readiness
- task capability selection readiness
- trusted runtime context validity
- setup blocking reasons
- declaration eligibility

Those node-local setup fields are part of the node's own status contract and are used to drive setup UX before or alongside Core-reported operational readiness.

## API Surface (Implemented Baseline)
Implemented Phase 2 API groups:
- capability declaration submission
- capability profile lookup/inspection
- governance bundle fetch/refresh
- node operational status query
- telemetry ingestion for lifecycle/governance signals

Capability responses and profile records now also publish the canonical taxonomy defined in:
- [Node Capability Taxonomy](./capability-taxonomy.md)

Exact request/response schemas are defined in:
- [Node Phase 2 Lifecycle Contract](./node-phase2-lifecycle-contract.md)

## Relationship to Existing Phase 1 Docs
- Phase 1 onboarding + trust activation contract: [node-onboarding-phase1-contract.md](./node-onboarding-phase1-contract.md)
- Node onboarding architecture baseline: [node-onboarding-registration-architecture.md](./node-onboarding-registration-architecture.md)
- Trust activation payload baseline: [node-trust-activation-payload-contract.md](./node-trust-activation-payload-contract.md)
