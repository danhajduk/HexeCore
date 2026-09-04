# Core API Router Ownership

Status: Implemented

Core composes the mixed node/system API through `core/backend/app/api/system.py`.
That file is intentionally small: it builds the behavior-preserving source
router in `core/backend/app/api/system_legacy.py`, then assigns routes to
explicit domain routers in `core/backend/app/api/system_domains/`.

Standalone Supervisor API routes are not Core router domains. Routes under
`/api/supervisor/*` are mounted by `core/backend/app/supervisor/server.py` or
the mirrored Supervisor package. Core-owned Supervisor visibility and control
wrappers live under `/api/system/supervisor*` and `/api/system/supervisors*`.

Domain ownership:

- `addons_runtime`: `/api/addons*` and `/api/system/addons/runtime*`
- `node_onboarding`: `/api/system/nodes/onboarding*` and hidden legacy `/api/system/ai-nodes/onboarding*`
- `node_reauth`: `/api/system/nodes/reauth*`
- `node_registrations`: node registrations, registry, trust status, and operational status
- `node_capabilities`: node capability declarations and capability profiles
- `node_budgets`: node budget declarations, policy, allocations, usage, top-up, reset, and override
- `node_services`: service resolution and service-token authorization
- `node_providers`: provider capability reporting, routing metadata, and provider model policy
- `node_governance`: governance bundle read and refresh endpoints
- `node_telemetry`: node telemetry ingestion
- `supervisor_fleet`: `/api/system/supervisor*` and `/api/system/supervisors*`

`tests/test_system_router_composition.py` verifies that the composed domain router preserves the same route path, method, schema visibility, and handler-name surface as the legacy source router.
