# Node Budget Management Contract

Status: Partially implemented
Last updated: 2026-03-20 09:20

## Purpose

Defines the current Core-owned contract for node budget policy, budget grants, capacity publication, usage reporting, and distribution behavior for trusted nodes.

Current implemented Core-side responsibilities:

- store node-declared budget capabilities and operator-configured budget settings
- derive versioned budget policy and grant material from node/customer/provider budget configuration
- fold budget policy into the node governance bundle
- expose node-facing budget-policy read and refresh endpoints
- publish retained MQTT budget-policy snapshots and revocations
- persist periodic node usage summaries by grant and period
- preserve the existing queue-reservation and per-job usage-report compatibility path
- persist provider/model routing metadata plus declared service/provider/model capacity metadata

Current node-runtime execution responsibility:

- local per-request budget enforcement against cached grants

That execution responsibility is **Not verifiable from current repository state** because the AI node runtime lives outside this repository. This document defines the Core-to-node contract the node runtime is expected to follow.

## Control Model

The current control-plane model is:

- node publishes budget capability support and provider/service capacity metadata
- Core owns budget policy, allocations, grant issuance, revocation, and governance versioning
- node consumes the issued governance and budget policy, caches grants locally, enforces them at execution time, and reports usage back to Core

Core remains the policy authority. The node is the intended budget enforcement point for individual executions. Core still retains a compatibility admission path for queue-based reservations so existing scheduler flows continue to work while node-local execution enforcement is adopted.

## Implemented Routes

### Budget Declaration And Admin Setup

- `POST /api/system/nodes/budgets/declaration`
- `GET /api/system/nodes/budgets`
- `GET /api/system/nodes/budgets/{node_id}`
- `PUT /api/system/nodes/budgets/{node_id}`
- `DELETE /api/system/nodes/budgets/{node_id}`
- `GET /api/system/nodes/budgets/{node_id}/customers`
- `PUT /api/system/nodes/budgets/{node_id}/customers/{customer_id}`
- `DELETE /api/system/nodes/budgets/{node_id}/customers/{customer_id}`
- `GET /api/system/nodes/budgets/{node_id}/providers`
- `PUT /api/system/nodes/budgets/{node_id}/providers/{provider_id}`
- `DELETE /api/system/nodes/budgets/{node_id}/providers/{provider_id}`
- `GET /api/system/nodes/budgets/{node_id}/usage`
- `GET /api/system/nodes/budgets/{node_id}/usage-reports`
- `GET /api/system/nodes/budgets/export`
- `POST /api/system/nodes/budgets/{node_id}/top-up`
- `POST /api/system/nodes/budgets/{node_id}/reset`
- `POST /api/system/nodes/budgets/{node_id}/override`
- `POST /api/system/nodes/budgets/{node_id}/force-release`

### Node Policy Read And Refresh

- `GET /api/system/nodes/budgets/policy/current?node_id=...`
- `POST /api/system/nodes/budgets/policy/refresh`

Auth: `X-Node-Trust-Token`

Current behavior:

- `GET` returns the effective budget policy, current governance version, current budget-policy version, and `refresh_interval_s=60`
- `POST` returns `updated=false` when the caller already has the current `budget_policy_version` and `governance_version`
- responses are cacheable for short-lived local caching only
- nodes in governance freshness state `outdated` are blocked from receiving new budget policy material until they refresh governance
- `critical` freshness is warning-only; `outdated` begins after 24 hours without governance refresh activity
- the intended recovery path is governance refresh first, then budget-policy fetch/refresh

### Node Usage Ingestion

- `POST /api/system/nodes/budgets/usage-summary`
- `POST /api/system/nodes/budgets/usage-report`

Auth: `X-Node-Trust-Token`

Current behavior:

- `usage-summary` is the canonical periodic grant-usage path
- `usage-report` remains implemented for per-job reservation reconciliation compatibility
- `usage-summary` may also carry optional `provider`, `model_id`, and `task_family` metadata for service-resolution and admin rollup views
- when a delegating node reports usage against a provider-owned grant, Core stores that summary under the grant owner node and preserves the reporting node id in metadata

### Node Service Resolution And Authorization

- `POST /api/system/nodes/services/resolve`
- `POST /api/system/nodes/services/authorize`

Auth: `X-Node-Trust-Token`

Current behavior:

- resolution returns service/provider candidates filtered by governance routing policy and current admissible budget state
- delegated service resolution evaluates admissibility against the provider node budget that owns the selected candidate
- authorization reuses the Core service-token issuer primitives and returns a short-lived token only when the selected candidate remains admissible

### Provider And Capacity Publication

- `POST /api/system/nodes/providers/capabilities/report`
- `GET /api/system/nodes/providers/routing-metadata`

Auth:

- provider report: `X-Node-Trust-Token`
- routing metadata read: admin auth

## Budget Policy Contract

`GET /api/system/nodes/budgets/policy/current` returns:

```json
{
  "ok": true,
  "node_id": "node-abc123",
  "governance_version": "gov-v8",
  "budget_policy_version": "nbp-2e8d51dd7e2a",
  "refresh_interval_s": 60,
  "budget_policy": {
    "node_id": "node-abc123",
    "service": "ai.inference",
    "status": "active",
    "budget_policy_version": "nbp-2e8d51dd7e2a",
    "governance_version": "gov-v8",
    "period_start": "2026-03-20T00:00:00+00:00",
    "period_end": "2026-03-21T00:00:00+00:00",
    "issued_at": "2026-03-20T07:10:00+00:00",
    "enforcement_mode": "hard_stop",
    "shared_customer_pool": false,
    "shared_provider_pool": false,
    "overcommit_enabled": false,
    "allowed_providers": ["openai", "anthropic"],
    "fallback_rules": {
      "distribution_mode": "push_first_poll_second",
      "allow_cached_grants_until_expiry": true,
      "queue_usage_reports_while_core_unavailable": true,
      "degrade_when_cached_grants_expire": true,
      "reconcile_poll_interval_s": 60
    },
    "grants": []
  }
}
```

Implemented `budget_policy.status` values:

- `active`
- `not_configured`

Current budget-policy versioning rules:

- `budget_policy_version` is a stable hash of the persisted declaration, config, allocations, reservations, and usage-summary bundle
- a governance reissue is triggered when the effective budget policy changes materially
- `governance_version` is echoed into both the top-level policy and each derived grant when governance embeds budget policy

## Grant Contract

Core derives a grant set from the configured node budget and each explicit customer/provider allocation.

Grant shape:

- `grant_id`
- `consumer_node_id`
- `service`
- `period_start`
- `period_end`
- `limits`
- `status`
- `scope_kind`
- `subject_id`
- `governance_version`
- `budget_policy_version`
- `metadata`
- `issued_at`

Implemented `status` values:

- `active`
- `expired`

Implemented `scope_kind` values:

- `node`
- `customer`
- `provider`

Current limit-family mapping:

- node or allocation money limit -> `limits.max_cost_cents`
- compute unit `tokens` -> `limits.max_tokens`
- compute unit `requests` -> `limits.max_requests`
- other compute units remain in `metadata.compute_unit` and `metadata.max_compute_units`

`max_bytes` is not emitted by current Core budget configuration because node-budget setup does not yet include a byte-budget field.

## Governance Integration

Budget policy is now part of the effective governance bundle issued by Core.

Implemented governance-bundle additions:

- `routing_policy_constraints.allowed_providers`
- `routing_policy_constraints.allowed_models`
- `routing_policy_constraints.allowed_task_families`
- `budget_policy`

Current rules:

- governance issuance is still the canonical Core-to-node policy channel
- governance refresh returns the latest budget-bearing governance bundle when capability, routing-policy, or budget-policy inputs change
- nodes can fetch budget policy directly through `/budgets/policy/*`, but the same effective policy is also embedded in governance
- governance freshness transitions are derived from existing governance timestamps, preferring refresh activity and falling back to issued time before the first refresh, audited as `node_governance_freshness_changed`, and surfaced in registry and operational-status views

## Capacity Declaration Contract

Trusted nodes can publish capacity metadata with `POST /api/system/nodes/providers/capabilities/report`.

Current implemented top-level capacity object:

```json
{
  "service": "ai.inference",
  "period": "daily",
  "limits": {
    "max_requests": 10000,
    "max_tokens": 1000000,
    "max_cost_cents": 2500
  },
  "concurrency": {
    "max_inflight_requests": 4
  },
  "sla_hints": {
    "availability_tier": "best_effort"
  }
}
```

Current implemented capacity publication scopes:

- top-level `service_capacity`
- provider item `capacity`
- model item `capacity`

Current validation rules:

- `limits` and `concurrency` are normalized as non-negative numeric maps
- `sla_hints` is normalized as a shallow JSON object of scalar or scalar-list values
- common limit keys include `max_requests`, `max_tokens`, `max_cost_cents`, `max_bytes`, and `max_compute_units`
- unrecognized `max_*` numeric keys are preserved

Current admin inspection behavior:

- `GET /api/system/nodes/providers/routing-metadata` returns `service_capacity`, `provider_capacity`, and `model_capacity` with each model row
- grouped node output also exposes node-level `service_capacity` and provider-level `capacity`

## Node Runtime Enforcement Contract

Status: Not verifiable from current repository state

The intended node runtime sequence is:

1. receive the execution request
2. validate trust/auth/governance context
3. resolve provider, model, and task-family
4. load the applicable cached grant set
5. check local usage counters for the current grant period
6. execute when within grant limits
7. record actual local usage
8. queue a periodic usage summary back to Core
9. reject or degrade when over budget or when all cached grants have expired

Core no longer needs to be queried synchronously for each request under this contract. Core remains the grant issuer and reconciliation authority.

## Service-Resolution Relationship

The current budget policy and grant system is also used by the node service-resolution flow.

Current behavior:

- Core resolves task-family requests against service catalog candidates
- Core computes an effective budget view for the selected service/provider/model using the current grant set
- nodes still enforce those grants locally at execution time
- Core authorization is only for issuing short-lived service tokens and does not replace local execution-time enforcement

## MQTT Distribution And Poll Fallback

Core publishes retained policy data to:

- `hexe/policy/grants/{node_id}`
- `hexe/policy/revocations/{node_id}`
- `hexe/policy/revocations/{grant_id}`

Current behavior:

- budget configuration changes publish a retained grant snapshot for the node
- budget deletion publishes retained revocation payloads for the node and each derived grant
- nodes should apply new grant versions atomically from the retained snapshot
- nodes should stop using revoked grants immediately when revocation messages arrive
- polling remains the fallback reconciliation path when MQTT delivery is delayed or missed

## Usage Reporting Contract

### Periodic Summary

`POST /api/system/nodes/budgets/usage-summary` accepts:

- `node_id`
- `service`
- `grant_id`
- `period_start`
- `period_end`
- `used_requests`
- `used_tokens`
- `used_cost_cents`
- `denials`
- `error_counts`
- `metadata`

This is the canonical periodic reporting shape for node budget grants in Core.

### Per-Job Compatibility Path

`POST /api/system/nodes/budgets/usage-report` still accepts:

- `node_id`
- `job_id`
- `status`
- `actual_money_spend`
- `actual_compute_spend`

This route remains the implemented compatibility path for reservation finalization and release in the queue-based scheduler flow.

### Telemetry Relationship

Node budget usage summaries remain a distinct Core ingestion path. They are not currently merged into the generic `/api/telemetry/usage` subsystem.

## Outage And Expiry Semantics

Implemented Core-issued fallback rules are:

- `distribution_mode=push_first_poll_second`
- `allow_cached_grants_until_expiry=true`
- `queue_usage_reports_while_core_unavailable=true`
- `degrade_when_cached_grants_expire=true`
- `reconcile_poll_interval_s=60`

This means the intended runtime behavior is:

- continue enforcing cached active grants locally while Core is unavailable
- queue periodic usage reports locally and retry later
- do not assume new grants or governance updates are available until Core returns
- degrade cleanly once cached grant periods expire without refresh

The Core side of that contract is implemented. The node-runtime side remains outside this repository.

## Scheduler Compatibility Path

Current queue-based scheduler behavior remains implemented:

- queue submit may still create Core-side reservations against node/customer/provider budgets
- queue cancel and queue completion still reconcile those reservations
- hard-stop admission still exists as a compatibility backstop for queue-driven work

This is a compatibility layer, not the long-term replacement for node-local grant enforcement.

## Audit Events

Current Core audit events include:

- `node_budget_capabilities_declared`
- `node_budget_configured`
- `node_budget_deleted`
- `node_budget_customer_allocation_upserted`
- `node_budget_customer_allocation_deleted`
- `node_budget_provider_allocation_upserted`
- `node_budget_provider_allocation_deleted`
- `node_budget_usage_reported`
- `node_budget_usage_summary_reported`
- `node_budget_reservation_created`
- `node_budget_reservation_denied`
- `node_budget_reservation_leased`
- `node_budget_reservation_finalized`
- `node_budget_reservation_released`
- `node_budget_topped_up`
- `node_budget_reset`
- `node_budget_override_set`
- `node_budget_reservation_force_released`
- `node_provider_capability_report_received`

## Code Anchors

- `backend/app/system/onboarding/node_budgeting.py`
- `backend/app/system/onboarding/governance.py`
- `backend/app/system/onboarding/model_routing_registry.py`
- `backend/app/system/onboarding/provider_capability_normalization.py`
- `backend/app/api/system.py`
- `frontend/src/core/pages/Addons.tsx`

## See Also

- [API Reference](../core/api/api-reference.md)
- [Node Provider Intelligence Contract](../core/api/node-provider-intelligence-contract.md)
- [Node Phase 2 Lifecycle Contract](./node-phase2-lifecycle-contract.md)
- [Node Onboarding API Contract](./node-onboarding-api-contract.md)
