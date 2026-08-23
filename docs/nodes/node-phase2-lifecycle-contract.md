# Node Phase 2 Lifecycle Contract

Status: Implemented
Last Updated: 2026-03-20 10:16

## Purpose

Defines the implemented Core-side Phase 2 lifecycle contract after node trust activation:

- capability declaration
- capability profile persistence
- governance issuance and refresh
- operational readiness state
- runtime telemetry ingestion

Public-facing naming note: Hexe Nodes / Hexe AI are display names only in this phase. Current API paths, trust tokens, and MQTT topic literals remain on the existing compatibility naming.

## Canonical Phase 2 Sequence

After Phase 1 trust activation, the canonical node readiness sequence is:

7. `Provider Setup` -> `capability_setup_pending`
8. `Capability Declaration` -> `capability_declaration_in_progress`
9. `Governance Sync` after accepted declaration -> `capability_declaration_accepted`
10. `Ready` -> `operational`

Current Core-to-node mapping:

- `Provider Setup`: node-local provider selection and provider readiness checks
- `Capability Declaration`: node submits its capability manifest to Core while effectively in `capability_declaration_in_progress`
- `Governance Sync`: node fetches or refreshes the effective governance bundle from Core after accepted declaration; current docs map accepted declaration to `capability_status=accepted`
- `Ready`: Core projects `operational_ready=true`, which corresponds to the canonical lifecycle target state `operational`

## Readiness Model

`operational_ready` is `true` only when all are true:

1. `trust_status == trusted`
2. `capability_status == accepted`
3. `governance_sync_status == issued`

Derived status fields exposed by node registry and operational-status APIs:

- `capability_status`: `missing | declared | accepted`
- `governance_sync_status`: `pending_capability | pending | issued`
- `operational_ready`: boolean
- `active_governance_version`: current governance version (or `null`)
- `governance_last_issued_at`: timestamp (or `null`)
- `governance_last_refresh_request_at`: timestamp (or `null`)
- `governance_freshness_state`: `pending | unknown | fresh | critical | outdated`
- `governance_freshness_changed_at`: timestamp of the last derived freshness-state transition
- `governance_stale_for_s`: age in seconds since the latest governance issue or refresh request
- `governance_outdated`: boolean convenience flag

Readiness projection note:

- `operational_ready` is the canonical Core-side readiness signal.
- `lifecycle_state` and `operational_ready` are related but not identical projections.
- In the current live system, Core can report `operational_ready=true` while the node-facing operational-status payload still carries `lifecycle_state=trusted`.
- Until a Core lifecycle-label normalization change is made, clients and operators should treat `operational_ready` as the source of truth for Phase 2 operational readiness.

## Lifecycle States

Status: Partially implemented

Phase 2 introduces or depends on these post-trust lifecycle states:

- `capability_setup_pending`
- `capability_declaration_in_progress`
- `capability_declaration_accepted`
- `capability_declaration_failed_retry_pending`
- `operational`
- `degraded`

`capability_setup_pending` is the expected blocked state while a trusted node has not yet completed capability acceptance and governance issuance.

Current implementation note:

- `capability_setup_pending`, `operational`, and `degraded` are clearly represented in current Core-side lifecycle docs
- `capability_declaration_in_progress`, `capability_declaration_accepted`, and `capability_declaration_failed_retry_pending` are the canonical node lifecycle states for Phase 2 documentation, but current Core APIs still expose the related projection mainly through `capability_status` and `operational_ready`

Trusted-startup fast path:

- On trusted restart, node runtime may resume through `trusted -> capability_setup_pending`.
- If the node already has an accepted capability profile and fresh governance for the active profile, startup can continue immediately to `operational` instead of remaining visibly paused in setup.
- This fast path depends on node-local resume checks in addition to Core's readiness projection, so Core docs should treat it as a valid startup continuation path rather than assuming every trusted restart remains blocked in setup.

Transition guidance:
- `capability_setup_pending -> operational` only when:
  - `capability_status=accepted`
  - `governance_sync_status=issued`
  - `operational_ready=true`
- canonical intermediate interpretation:
  - `capability_setup_pending -> capability_declaration_in_progress`
  - successful declaration + accepted capability profile -> `capability_declaration_accepted`
  - failed declaration awaiting retry -> `capability_declaration_failed_retry_pending`
  - accepted declaration + issued governance + `operational_ready=true` -> `operational`
- failure to complete declaration or governance sync keeps the node non-operational and may surface degraded indicators

## API Contract

### Capability Declaration

- `POST /api/system/nodes/capabilities/declaration`
- Auth: `X-Node-Trust-Token`
- Request:
  - `manifest.manifest_version`
  - `manifest.node.node_id`
  - `manifest.node.node_type`
  - `manifest.node.node_name`
  - `manifest.node.node_software_version`
  - `manifest.declared_task_families[]`
  - `manifest.supported_providers[]`
  - `manifest.enabled_providers[]`
  - `manifest.node_features.telemetry`
  - `manifest.node_features.governance_refresh`
  - `manifest.node_features.lifecycle_events`
  - `manifest.node_features.provider_failover`
  - `manifest.environment_hints.deployment_target`
  - `manifest.environment_hints.acceleration`
  - `manifest.environment_hints.network_tier`
  - `manifest.environment_hints.region`
- Success response:
  - `acceptance_status: accepted`
  - `node_id`
  - `manifest_version`
  - `accepted_at`
  - `declared_capabilities[]`
  - `enabled_providers[]`
  - `capability_profile_id`
  - `governance_version`
  - `governance_issued_at`

### Capability Profile Registry

- `GET /api/system/nodes/capabilities/profiles?node_id=...` (admin auth)
- `GET /api/system/nodes/capabilities/profiles/{profile_id}` (admin auth)
- Returns immutable accepted profile records including normalized capability fields and `declaration_raw`.

### Governance Bundle Fetch

- `GET /api/system/nodes/governance/current?node_id=...`
- Auth: `X-Node-Trust-Token`
- Requires trusted node and accepted capability profile.
- Success response:
  - `node_id`
  - `capability_profile_id`
  - `governance_version`
  - `issued_timestamp`
  - `refresh_interval_s`
  - `governance_bundle`

Current implemented governance-bundle sections include:

- `node_class_rules`
- `feature_gating_defaults`
- `telemetry_requirements`
- `capability_usage_constraints`
- `routing_policy_constraints`
- `budget_policy`

### Governance Refresh

- `POST /api/system/nodes/governance/refresh`
- Auth: `X-Node-Trust-Token`
- Request:
  - `node_id`
  - `current_governance_version` (optional)
- Response when changed:
  - `updated: true`
  - `governance_version`
  - `governance_bundle`
  - `refresh_interval_s`
- Response when unchanged:
  - `updated: false`
  - `governance_version`
  - `refresh_interval_s`

Current refresh behavior:

- governance is reissued when capability profile, routing-policy constraints, or embedded budget policy changes materially
- budget policy remains readable through `/api/system/nodes/budgets/policy/*`, but governance remains the canonical Core-to-node policy bundle
- governance freshness is derived from existing governance timestamps, preferring the latest refresh request and falling back to issued time before the first refresh, not from a separate heartbeat protocol
- freshness thresholds are currently:
  - `critical` after 6 hours without governance refresh activity
  - `outdated` after 24 hours without governance refresh activity
- `GET /api/system/nodes/governance/current` and `POST /api/system/nodes/governance/refresh` remain the recovery path for stale nodes; those routes record refresh activity before freshness is re-evaluated

### Operational Status

- `GET /api/system/nodes/operational-status/{node_id}`
- Auth: either `X-Node-Trust-Token` or admin auth/session.
- Response:
  - `node_id`
  - `lifecycle_state`
  - `trust_status`
  - `capability_status`
  - `governance_status`
  - `operational_ready`
  - `active_governance_version`
  - `last_governance_issued_at`
  - `last_governance_refresh_request_at`
  - `governance_freshness_state`
  - `governance_freshness_changed_at`
  - `governance_stale_for_s`
  - `governance_outdated`
  - `last_telemetry_timestamp`
  - `updated_at`

This endpoint is also the canonical polling contract for setup-state progression and operational readiness checks.

Freshness-state meaning:

- `fresh`: governance activity is within the expected freshness window
- `critical`: governance has not refreshed for at least 6 hours and operator warning should be shown
- `outdated`: governance has not refreshed for at least 24 hours; the node remains visible to operators but Core blocks new budget-policy reads and new node-to-service resolution or authorization material until governance is refreshed again

Node UI setup/readiness payload note:

- The AI-node operator UI also consumes node-local setup payload details in addition to this Core endpoint.
- Current node-local status payload includes a `capability_setup` object with:
  - `readiness_flags.trust_state_valid`
  - `readiness_flags.node_identity_valid`
  - `readiness_flags.provider_selection_valid`
  - `readiness_flags.task_capability_selection_valid`
  - `readiness_flags.core_runtime_context_valid`
  - `provider_selection.configured`
  - `provider_selection.enabled_count`
  - `provider_selection.enabled[]`
  - `provider_selection.supported.{cloud,local,future}[]`
  - `task_capability_selection.configured`
  - `task_capability_selection.selected_count`
  - `task_capability_selection.selected[]`
  - `task_capability_selection.available[]`
  - `blocking_reasons[]`
  - `declaration_allowed`
- Core's `operational-status` contract remains the canonical readiness projection API, while the node-local setup payload is the canonical source for operator-facing setup gating details such as task capability selection readiness.

Provider-setup note:

- `Provider Setup` is currently reflected through the node-local `capability_setup.provider_selection` and related readiness flags rather than a dedicated Core-side provider-setup route
- Core readiness depends on the later accepted capability declaration and governance issuance, while the node-local setup payload is the canonical operator view of provider readiness before declaration

### Telemetry Ingestion

- `POST /api/system/nodes/telemetry`
- Auth: `X-Node-Trust-Token`
- Request:
  - `node_id`
  - `event_type` (allowed: `lifecycle_transition`, `degraded_state`, `capability_declaration_success`, `governance_sync`)
  - `event_state` (optional)
  - `message` (optional)
  - `payload` (optional, lightweight JSON object)
- Success response:
  - `node_id`
  - `event_type`
  - `received_at`

## See Also

- [Node Capability Activation Architecture (Phase 2)](./node-capability-activation-architecture.md)
- [API Reference](../core/api/api-reference.md)
- [Node Onboarding Phase 1 Contract](./node-onboarding-phase1-contract.md)
