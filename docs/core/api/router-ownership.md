# Core API Router Ownership

Status: Implemented

Core composes the mixed node/system API through `backend/app/api/system.py`. That file is intentionally small: it builds the behavior-preserving source router in `backend/app/api/system_legacy.py`, then assigns routes to explicit domain routers in `backend/app/api/system_domains/`.

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

`tests/test_system_router_composition.py` verifies that the composed domain router preserves the same route path, method, schema visibility, and handler-name surface as the legacy source router.
