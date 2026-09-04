# Hexe Core API Reference

Core routes are mounted by `core/backend/app/main.py` and are represented in
`openapi-paths.snapshot.json`. Standalone Supervisor routes under
`/api/supervisor/*` are mounted by the Supervisor API service, not by Core; they
are listed here only where Core wraps or depends on them operationally.

## Conventions

- Admin-protected endpoints require admin authentication/session.
- Some route families include compatibility aliases for legacy clients.
- MQTT routes are mounted under `/api/system`.
- [Generated OpenAPI Paths](./generated-openapi-paths.md) lists every path in
  the deterministic Core OpenAPI snapshot.

## Runtime Proxy Surfaces

Status: Implemented

Dynamic proxy routes are runtime surfaces, but they are intentionally not treated
as stable generated-client operations in the OpenAPI path snapshot. Their target
paths are resolved from trusted node registration metadata or addon registry
metadata at request time.

- Node UI proxy: `/nodes/{node_id}/ui/` and `/nodes/{node_id}/ui/{path}`
- Node API proxy: `/api/nodes/{node_id}/{path}`
- Addon UI proxy: `/addons/{addon_id}/` and `/addons/{addon_id}/{path}`
- Addon API proxy: `/api/addons/{addon_id}/{path}`
- Legacy UI redirects: `/ui/nodes/...` and `/ui/addons/...`

The detailed proxy contract is documented in
[Proxied UI Contract](../frontend/proxied-ui-contract.md),
[Proxied UI Metadata](./proxied-ui-metadata.md), and
[Frontend And UI](../frontend/frontend-and-ui.md).

## Core System APIs

Status: Implemented

- Health and stats:
  - `GET /api/health`
  - `GET /api/system/stats/current`
  - `GET /api/system-stats/current`
  - `GET /api/system/stack/summary`
- Settings and repo/system status:
  - `GET /api/system/platform`
  - `GET /api/system/settings`
  - `PUT /api/system/settings/{key}`
  - `GET /api/system/repo/status`
- Edge gateway:
  - `GET /api/edge/status`
  - `GET /api/edge/publications`
  - `POST /api/edge/publications` (admin session/token required)
  - `PATCH /api/edge/publications/{publication_id}` (admin session/token required)
  - `DELETE /api/edge/publications/{publication_id}` (admin session/token required)
  - `GET /api/edge/public-identity`
  - `GET /api/edge/cloudflare/settings`
  - `PUT /api/edge/cloudflare/settings` (admin session/token required)
  - `POST /api/edge/reconcile` (admin session/token required)
  - `POST /api/edge/cloudflare/test` (admin session/token required)
- Events/services:
  - `GET /api/system/events`
  - `POST /api/system/nodes/onboarding/sessions` (request may include optional `hostname`, optional absolute `ui_endpoint`, and optional absolute `api_base_url` for node-hosted UI/API discovery)
  - `GET /api/system/nodes/onboarding/sessions` (admin session/token required)
  - `GET /api/system/nodes/onboarding/sessions/{session_id}` (admin session/token required)
  - `POST /api/system/nodes/onboarding/sessions/{session_id}/approve` (admin session/token required)
  - `POST /api/system/nodes/onboarding/sessions/{session_id}/reject` (admin session/token required)
  - `POST /api/system/nodes/onboarding/sessions/cancel-active` (admin session/token required; cancels all active `pending` and `approved` onboarding sessions)
  - `GET /api/system/nodes/onboarding/sessions/{session_id}/finalize?node_nonce=...`
  - `POST /api/system/nodes/reauth/sessions` (existing node starts a re-auth session for migration/recovery and receives an approval URL)
  - `GET /api/system/nodes/reauth/sessions/{session_id}` (admin session/token required; approval URL state required)
  - `POST /api/system/nodes/reauth/sessions/{session_id}/approve` (admin session/token required; approval URL state required)
  - `POST /api/system/nodes/reauth/sessions/{session_id}/reject` (admin session/token required; approval URL state required)
  - `GET /api/system/nodes/reauth/sessions/{session_id}/finalize?node_nonce=...` (returns fresh trust activation material after approval)
  - `PUT /api/system/nodes/registrations/{node_id}/metadata` (admin session/token required; refreshes full node-owned endpoint/UI metadata without changing trust or identity)
  - `GET /api/system/nodes/registrations` (admin session/token required)
  - `GET /api/system/nodes/registrations/{node_id}` (admin session/token required)
  - `DELETE /api/system/nodes/registrations/{node_id}` (admin session/token required)
  - `POST /api/system/nodes/registrations/{node_id}/revoke` (admin session/token required; `/untrust` alias preserved for compatibility)
  - `GET /api/system/nodes/trust-status/{node_id}` (node trust token or admin session/token; explicit trust/revocation/removal status)
  - `GET /api/system/nodes/registry` (admin session/token required; includes capability/governance/readiness status fields)
  - `POST /api/system/nodes/budgets/declaration` (trusted node token required via `X-Node-Trust-Token`; node-declared budget capability contract)
  - `GET /api/system/nodes/budgets` (admin session/token required; budget declaration + setup overview)
  - `GET /api/system/nodes/budgets/{node_id}` (trusted node token or admin session/token; node budget bundle)
  - `PUT /api/system/nodes/budgets/{node_id}` (admin session/token required; operator budget setup)
  - `DELETE /api/system/nodes/budgets/{node_id}` (admin session/token required; remove configured budget while preserving node declaration)
  - `GET /api/system/nodes/budgets/{node_id}/customers` (admin session/token required)
  - `PUT /api/system/nodes/budgets/{node_id}/customers/{customer_id}` (admin session/token required)
  - `DELETE /api/system/nodes/budgets/{node_id}/customers/{customer_id}` (admin session/token required)
  - `GET /api/system/nodes/budgets/{node_id}/providers` (admin session/token required)
  - `PUT /api/system/nodes/budgets/{node_id}/providers/{provider_id}` (admin session/token required)
  - `DELETE /api/system/nodes/budgets/{node_id}/providers/{provider_id}` (admin session/token required)
  - `GET /api/system/nodes/budgets/{node_id}/usage` (admin session/token required; usage summary, remaining budget, next reset)
  - `GET /api/system/nodes/budgets/{node_id}/usage-reports` (admin session/token required; periodic grant usage summaries)
  - `GET /api/system/nodes/budgets/export` (admin session/token required; budget usage export in JSON or CSV)
  - `GET /api/system/nodes/budgets/policy/current?node_id=...` (trusted node token required via `X-Node-Trust-Token`; current effective budget policy and grants; returns `409 node_governance_outdated` when governance freshness is outdated)
  - `POST /api/system/nodes/budgets/policy/refresh` (trusted node token required via `X-Node-Trust-Token`; version-aware budget policy refresh; blocked while governance freshness is outdated)
  - `POST /api/system/nodes/budgets/{node_id}/top-up` (admin session/token required)
  - `POST /api/system/nodes/budgets/{node_id}/reset` (admin session/token required)
  - `POST /api/system/nodes/budgets/{node_id}/override` (admin session/token required)
  - `POST /api/system/nodes/budgets/usage-summary` (trusted node token required via `X-Node-Trust-Token`; periodic usage summary by grant/period with optional provider/model/task-family metadata)
  - `POST /api/system/nodes/services/resolve` (trusted node token required via `X-Node-Trust-Token`; node-aware task-family to service/provider resolution using governance and budget policy; blocked while governance freshness is outdated)
  - `POST /api/system/nodes/services/authorize` (trusted node token required via `X-Node-Trust-Token`; short-lived service token issuance gated by resolution and effective budget; blocked while governance freshness is outdated)
  - `POST /api/system/nodes/capabilities/declaration` (trusted node token required via `X-Node-Trust-Token`)
  - `POST /api/system/nodes/providers/capabilities/report` (trusted node token required via `X-Node-Trust-Token`; provider/model capability plus service/provider/model capacity ingestion)
  - `GET /api/system/nodes/providers/routing-metadata` (admin session/token required; model cost/latency + declared capacity + node availability view)
  - `GET /api/system/nodes/providers/model-policy` (admin session/token required)
  - `PUT /api/system/nodes/providers/model-policy/{provider}` (admin session/token required)
  - `DELETE /api/system/nodes/providers/model-policy/{provider}` (admin session/token required)
  - `GET /api/system/nodes/governance/current?node_id=...` (trusted node token required via `X-Node-Trust-Token`; governance bundle now includes routing-policy constraints and budget policy when available; also acts as a governance freshness recovery path)
  - `POST /api/system/nodes/governance/refresh` (trusted node token required; version-aware governance refresh across capability, routing-policy, and budget-policy changes; also clears `outdated` state when successful)
  - `GET /api/system/nodes/operational-status/{node_id}` (node trust token or admin session/token; lightweight lifecycle/capability/governance status, including governance freshness and outdated flags)
  - `POST /api/system/nodes/telemetry` (trusted node token required; runtime lifecycle/governance signal ingestion)
  - `GET /api/system/nodes/hardware/access-requests/schema` (public discovery endpoint; returns the JSON Schema for node hardware access requests plus supported hardware resources and operations)
  - `GET /api/system/nodes/hardware/ble/provisioning/schemas/{node_profile_id}` (public discovery endpoint; returns the provisioning payload schema for a supported node profile such as Voice)
  - `POST /api/system/nodes/hardware/bluetooth/ble/scan` (trusted node token required via `X-Node-Trust-Token`; Core fans a UUID-filtered BLE scan out to online trusted Bluetooth supervisors, issues and releases per-supervisor leases, and returns aggregated matches)
  - `POST /api/system/nodes/hardware/access-requests` (trusted node token required via `X-Node-Trust-Token`; request Core-governed host hardware access such as Bluetooth BLE status, scan, or Wi-Fi provisioning)
  - `GET /api/system/nodes/{node_id}/hardware/access-requests` (trusted node token required via `X-Node-Trust-Token`; list the node's hardware requests and lease state without returning lease tokens)
  - `POST /api/system/nodes/hardware/leases/{lease_id}/release` (trusted node token required via `X-Node-Trust-Token`; release a granted hardware lease)
  - `GET /api/system/hardware/access-requests` (admin session/token required; list hardware access requests, with optional `status` filter)
  - `POST /api/system/hardware/access-requests/{request_id}/decision` (admin session/token required; approve or deny a pending hardware request created under `ask` policy)
  - `POST /api/system/hardware/leases/validate` (admin session/token or Supervisor reporting token required; validates signed hardware lease tokens against persisted Core lease state)
  - `GET /api/system/nodes/capabilities/profiles` (admin session/token required)
  - `GET /api/system/nodes/capabilities/profiles/{profile_id}` (admin session/token required)
  - `POST /api/services/register`
  - `GET /api/services/resolve`
- Node registry and Core-rendered node UI:
  - `GET /api/nodes`
  - `GET /api/nodes/{node_id}`
  - `GET /api/nodes/{node_id}/ui-manifest` (admin session/token required; Core fetches `GET /api/node/ui-manifest` from trusted nodes, validates it, and returns an operator-readable fetch state)
- Core Supervisor fleet/runtime:
  - `GET /api/system/supervisor/resources/history` (admin session/token required; local configured Supervisor host resource history)
  - `GET /api/system/supervisor/runtimes/{node_id}/resources/history` (admin session/token required; local configured Supervisor runtime resource history)
  - `GET /api/system/supervisors` (admin session/token required; hides long-offline remote Supervisors by default)
  - `GET /api/system/supervisors?include_historical=true` (admin session/token required; includes long-offline records marked with `visibility_state: "historical"`)
  - `GET /api/system/supervisors/{supervisor_id}` (admin session/token required)
  - Core refreshes stored Supervisor version audit metadata on startup and every 10 minutes by default; `metadata.version_audit` is advisory and separate from freshness.
  - `GET /api/system/supervisors/{supervisor_id}/update/status` (admin session/token required; reads the Supervisor-local update status for an online local or remote Supervisor and stores a sanitized status snapshot in fleet metadata)
  - `POST /api/system/supervisors/{supervisor_id}/update/start` (admin session/token required; validates the online Supervisor's supported update modes, forwards a bounded git self-update request or builds/uploads a `core_host` Supervisor source package, and records a sanitized audit/status result)
  - `GET /api/system/supervisors/{supervisor_id}/resources/history` (admin session/token required; local or remote Supervisor host resource history)
  - `GET /api/system/supervisors/{supervisor_id}/runtimes/{node_id}/resources/history` (admin session/token required; local or remote Supervisor runtime resource history)
  - `POST /api/system/supervisors/enrollment-tokens` (admin session/token required; creates a short-lived one-time Supervisor enrollment token)
  - `POST /api/system/supervisors/enroll` (one-time enrollment token required in the JSON body; consumes the token and returns a Supervisor reporting token)
  - `POST /api/system/supervisors/register` (`X-Admin-Token` or issued `X-Supervisor-Token` required)
  - `POST /api/system/supervisors/heartbeat` (`X-Admin-Token` or issued `X-Supervisor-Token` required)
  - `DELETE /api/system/supervisors/{supervisor_id}` (admin session/token required)
- Standalone Supervisor Bluetooth broker:
  - `POST /api/supervisor/hardware/bluetooth/ble/status` (Core-issued hardware lease token required in JSON body; returns adapter state)
  - `POST /api/supervisor/hardware/bluetooth/ble/scan` (Core-issued hardware lease token required in JSON body; performs bounded BLE scan through Supervisor-managed `bluetoothctl`)
  - `POST /api/supervisor/hardware/bluetooth/ble/provision-wifi` (Core-issued `ble.provision_wifi` hardware lease token required in JSON body; validates the Voice provisioning context, encrypts the Voice payload into the BLE provisioning envelope, and delegates only the envelope to the Supervisor BLE GATT backend)
- Standalone Supervisor update:
  - `GET /api/supervisor/update/status` (reports Supervisor-local git/updater capability and current or last update state)
  - `POST /api/supervisor/update/start` (starts the bounded `hexe-updater.service` git update path when supported, or validates/stages/applies a Core-built `core_host` Supervisor source package)

Core fleet update orchestration uses the local Supervisor client for attached local Supervisors and each remote Supervisor's registered `api_base_url` for remote Supervisors. Update commands fail closed when the fleet record is not `online`, the remote API URL is missing, the Supervisor does not expose the update API, the requested `source_mode` is not in the Supervisor's advertised `supported_modes`, or a Core-host package cannot be built from the configured source root.

The end-to-end update workflow is documented in [Remote Supervisor Update Workflow](../../supervisor/remote-update-workflow.md).

Bluetooth hardware access is documented in [Node Hardware Access](../node-hardware-access.md). Core governs request/lease state; Supervisor enforces leases locally. Nodes do not receive raw host Bluetooth device or DBus access.

Platform metadata currently includes:

- `core_id`
- `platform_name`
- `platform_short`
- `platform_domain`
- `core_name`
- `supervisor_name`
- `nodes_name`
- `addons_name`
- `docs_name`
- `legacy_internal_namespace`
- `legacy_compatibility_note`
- `public_hostname`
- `public_ui_hostname`
- `public_api_hostname`

## Addon APIs

Status: Implemented

- Addon inventory/runtime:
  - `GET /api/addons`
  - `GET /api/addons/errors`
  - `GET /api/system/addons/runtime`
- Registry/admin:
  - `GET /api/addons/registry`
  - `POST /api/addons/registry/{addon_id}/register`
  - `GET /api/admin/addons/registry`

Registry payloads include canonical UI proxy metadata for Core-managed embedding:
- addons: `ui_enabled`, `ui_base_url`, `ui_mode`
- nodes: `ui_enabled`, `ui_base_url`, `ui_mode`, `ui_health_endpoint`, `api_base_url`
- the broader proxied-UI metadata contract, fail-safe defaults, and reserved extension fields are documented in [Proxied UI Metadata](./proxied-ui-metadata.md)
- Install sessions:
  - `POST /api/addons/install/start`
  - `GET /api/addons/install/{session_id}`
  - `POST /api/addons/install/{session_id}/permissions/approve`
  - `POST /api/addons/install/{session_id}/deployment/select`
  - `POST /api/addons/install/{session_id}/configure`
  - `POST /api/addons/install/{session_id}/verify`

## MQTT APIs

Status: Partially implemented

Representative routes under `/api/system`:
- setup/control: `/mqtt/status`, `/mqtt/setup-summary`, `/mqtt/setup/apply`, `/mqtt/setup/test-connection`, `/mqtt/setup-state`
- runtime: `/mqtt/runtime/health`, `/mqtt/runtime/start`, `/mqtt/runtime/stop`, `/mqtt/runtime/init`, `/mqtt/runtime/rebuild`, `/mqtt/runtime/config`
- approvals/principals/users: `/mqtt/registrations/*`, `/mqtt/node-bridge-grants*`, `/mqtt/principals*`, `/mqtt/users*`, `/mqtt/generic-users*`
- node bridge credential claim: `POST /mqtt/node-bridge-grants/{grant_id}/credential/claim` with `X-Node-Id` and `X-Node-Trust-Token`
- observability/audit: `/mqtt/noisy-clients*`, `/mqtt/observability`, `/mqtt/audit`
- debug: `/mqtt/debug/*`
- notification dev hook: `POST /mqtt/debug/notifications/test-flow` (admin token required; only active when `NOTIFICATION_DEBUG_ENABLED=true`)

Deprecated/legacy compatibility endpoints:
- `/api/system/runtime/*` aliases mirror `/api/system/mqtt/runtime/*` for compatibility.
- mixed snake/camel compatibility aliases are preserved in selected principal endpoints.
- `/api/system/ai-nodes/onboarding/sessions*` aliases mirror global node onboarding routes and emit `Deprecation` + `Sunset` headers.

## Auth and User APIs

Status: Implemented

- Admin session:
  - `POST /api/admin/session/login`
  - `POST /api/admin/session/login-user`
  - `GET /api/admin/session/status`
  - `POST /api/admin/session/logout`
  - `POST /api/admin/reload`
  - `GET /api/admin/reload/status`
- Admin users:
  - `GET /api/admin/users`
  - `POST /api/admin/users`
  - `DELETE /api/admin/users/{username}`
- Service token:
  - `POST /api/auth/service-token`
  - `POST /api/auth/service-token/rotate`

Service token issuance modes:
- admin token or admin session may issue service tokens
- service principals may also issue constrained service tokens using `X-Service-Principal-Id` and `X-Service-Principal-Secret`

## Runtime And Health APIs

Status: Implemented

- Core internal scheduler status is exposed at `/api/system/scheduler/internal`.
- Core does not expose job queue, lease, worker, or job-history endpoints.
- Stack/system health and metrics endpoints under `/api/system/*` and `/api/system-stats/*`.
- Store lifecycle and status routes under `/api/store/*`.

## Telemetry APIs

Status: Implemented

- Usage telemetry:
  - `POST /api/telemetry/usage` (service token with `telemetry.write` scope required)
  - `GET /api/telemetry/usage`
  - `GET /api/telemetry/usage/stats`

Request model for `POST /api/telemetry/usage`:
- `service`
- `consumer_addon_id`
- `grant_id` (optional)
- `usage_units`
- `request_count`
- `period_start` (optional)
- `period_end` (optional)
- `metadata`

## Planned

Status: Not developed

- Formal OpenAPI-focused endpoint stability tiers.
- Explicit deprecation lifecycle metadata per endpoint group.

## See Also

- [Core Platform](./core-platform.md)
- [Core Communication API Guide](./core-communication-api-guide.md)
- [Edge Gateway](./edge-gateway.md)
- [Phase 5 Cloudflare Auto-Provisioning](../../migration/phase-5-cloudflare-auto-provisioning.md)
- [Node Provider Intelligence Contract](./node-provider-intelligence-contract.md)
- [Node Service Resolution And Budgeting](../node-service-resolution-and-budgeting.md)
- [Telemetry And Usage](./telemetry-and-usage.md)
- [MQTT Platform](../../mqtt/mqtt-platform.md)
- [Node Bridge Topic Grants](../../mqtt/node-bridge-topic-grants.md)
- [Notifications Bus](../../mqtt/notifications.md)
- [Auth and Identity](./auth-and-identity.md)
- [Runtime and Supervision](../../supervisor/runtime-and-supervision.md)
- [Node Onboarding API Contract](../../nodes/node-onboarding-api-contract.md)
- [Node Trust Activation Payload Contract](../../nodes/node-trust-activation-payload-contract.md)
- [Node Trust Status Contract](../../nodes/node-trust-status-contract.md)
- [Node Budget Management Contract](../../nodes/node-budget-management-contract.md)
- [Node Phase 2 Lifecycle Contract](../../nodes/node-phase2-lifecycle-contract.md)
- [Node Onboarding Migration Guide](../../nodes/node-onboarding-migration-guide.md)
