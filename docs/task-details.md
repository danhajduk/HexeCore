## Task 320-332
Original task details preserved from the oversized node service-resolution planning block formerly embedded in `docs/New_tasks.txt`.

Alignment notes after code audit:

- Already implemented and should be reused:
  - generic service discovery route: `GET /api/services/resolve`
    - source: `backend/app/system/services/router.py`
  - persisted service catalog store and registration path
    - source: `backend/app/system/services/store.py`
    - source: `POST /api/services/register`
  - Core-issued service tokens
    - source: `POST /api/auth/service-token`
  - node budget policy, derived grants, and budget-bearing governance bundle
    - source: `backend/app/system/onboarding/node_budgeting.py`
    - source: `backend/app/system/onboarding/governance.py`
  - trusted-node budget policy read/refresh endpoints
    - source: `GET /api/system/nodes/budgets/policy/current`
    - source: `POST /api/system/nodes/budgets/policy/refresh`
  - trusted-node periodic usage summaries
    - source: `POST /api/system/nodes/budgets/usage-summary`
  - retained grant/revocation distribution
    - source: `backend/app/system/policy/router.py`
    - source: node-budget retained topics in `backend/app/api/system.py`

- Not yet implemented and still needed:
  - node-aware service resolution endpoint using node trust, governance, allowed providers/models, and effective grants
  - node-aware authorization endpoint that issues a short-lived service token after resolution and policy checks
  - service-catalog extension for richer provider/model/service metadata where needed by node resolution
  - filtered effective-budget selection for task-family/provider/model decisions
  - end-to-end tests and docs for the above flow

- Explicit normalization rules retained from the original task notes:
  - keep task family ids semantic and stable
  - do not encode provider or context inside canonical task-family ids
  - keep task family, provider access, and model policy as separate concepts
  - keep governance as the canonical Core-to-node policy carrier
  - keep Core out of the execution hot path

- Removed from the queue as already covered by current code/contracts:
  - creating a second standalone node grant protocol from scratch
  - creating a second budget usage reporting protocol from scratch
  - creating a second governance carrier for budget policy
  - recreating service catalog storage from scratch
  - recreating retained grant/revocation topic structure from scratch

## Task 753-762
Original task details preserved from the proxied UI contract planning block formerly embedded in `docs/New_tasks.txt`.

Active normalized queue entries:

- Task 753: Define frontend path-prefix behavior requirements
- Task 754: Define frontend API base-path requirements
- Task 755: Define websocket proxy compatibility requirements
- Task 756: Define forwarded-header contract from Core to proxied targets
- Task 757: Define runtime config injection contract for proxied UIs
- Task 758: Define redirect and link-generation behavior for proxied targets
- Task 759: Define compatibility requirements for SPA-based UIs
- Task 760: Define compatibility requirements for server-rendered UIs
- Task 761: Add compatibility validation checks in Core for proxied UI targets
- Task 762: Add proxied UI author documentation and examples

Preserved details:

- Task 753 covers frontend routing, static assets, internal navigation, redirects, and deep-link reload behavior for proxied UIs mounted under `/nodes/{node_id}/ui/` and `/addons/{addon_id}/`, with rules against hardcoded root paths and expectations for SPA basename or server root-path support.
- Task 754 covers browser API traffic staying on `/api/nodes/{node_id}/...` and `/api/addons/{addon_id}/...`, runtime config guidance for `public_ui_base_path`, `public_api_base_path`, `websocket_base_path`, and avoiding direct browser use of `ui_base_url` or LAN addresses.
- Task 755 covers websocket URL derivation from the Core public origin, path-prefix preservation, secure `wss` upgrades under HTTPS, and avoiding hardcoded internal websocket hosts.
- Task 756 covers the forwarded-header contract for `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Prefix`, plus contextual headers like `X-Hexe-Node-Id`, `X-Hexe-Addon-Id`, and `X-Request-Id`.
- Task 757 covers runtime config injection for proxied UIs, including public origin, UI/API base paths, websocket base path, mount kind, and mount id, delivered via inline JSON, dedicated config endpoint, or server-rendered template injection without leaking internal URLs.
- Task 758 covers redirect and link-generation behavior so upstreams preserve the Core public prefix, avoid redirecting to internal `ui_base_url`, and allow Core to rewrite unsafe `Location` headers when needed.
- Task 759 covers SPA-specific compatibility guidance for React/Vite-style apps, including configurable router basename, asset base path, runtime API base injection, nested-route reload support, and avoiding embedded direct hostnames.
- Task 760 covers server-rendered UI compatibility guidance for FastAPI, Flask, Django, and similar frameworks, including configurable root path, forwarded prefix support, relative links/redirects, and prefix-aware asset serving.
- Task 761 covers compatibility validation checks for proxied UI targets, including `ui_enabled`, valid/reachable `ui_base_url`, optional health checks, `ui_supports_prefix`, required metadata presence, fail-closed behavior, and operator-facing error reasons.
- Task 762 covers the author-facing documentation bundle: route model, path-prefix rules, API base rules, websocket behavior, forwarded headers, runtime config, redirect behavior, common failure cases, checklist, and examples.

## Task 763-776
Original task details preserved from the "FastAPI Implementation Skeleton for Proxied UIs" block formerly embedded in `docs/New_tasks.txt`.

Queue cleanup disposition:

- Removed from the active queue as superseded by completed Task 738-750 implementation work already landed in the repository.

Superseded mapping:

- Task 763 superseded by completed shared HTTP proxy service work (Tasks 739 and 743-744 alignment).
- Task 764 superseded by completed websocket proxy support work (Task 740).
- Task 765 remains active because unified target resolution is still a distinct follow-up concern.
- Task 766 superseded by completed node UI proxy route work (Task 741).
- Task 767 superseded by completed node API proxy route work (Task 742).
- Task 768 superseded by completed addon UI proxy route work (Task 743).
- Task 769 superseded by completed addon API proxy route work (Task 744).
- Task 770 superseded by completed websocket route support work (Task 740).
- Task 771 superseded by completed redirect/prefix-safe proxy response handling work already reflected in the current proxy stack.
- Task 772 superseded by completed timeout/failure configuration work (Task 746).
- Task 773 superseded by completed structured logging work (Task 749).
- Task 774 superseded by completed availability/fallback handling work (Tasks 746 and 748).
- Task 775 superseded by completed HTTP proxy validation coverage (Task 750).
- Task 776 superseded by completed websocket proxy validation coverage (Task 750).

Preserved implementation skeleton notes:

- The removed block described reusable HTTP and websocket proxy modules, target resolution, node/addon UI and API routes, redirect-safe handling, timeout and size limits, structured logging, availability/error handling, and integration tests.
- Those concepts remain represented in the current codebase and completion log; they were removed from `docs/New_tasks.txt` only because they duplicate already completed queue items.

## Task 777
Original task detail preserved from the trailing line formerly embedded in `docs/New_tasks.txt`.

- Task 777: update or create JSON schemas in `docs/json_schema/`

## Task 778-781
Original task details preserved from the node API metadata follow-up queue added after the proxied UI contract work.

Active normalized queue entries:

- Task 778: Add canonical node api_base_url onboarding and registration metadata
- Task 779: Route node API proxy through canonical api_base_url metadata
- Task 780: Expose node api_base_url in admin/operator UI surfaces
- Task 781: Document and schema-update the canonical node API metadata contract

Preserved details:

- Task 778 adds a first-class node `api_base_url` contract to onboarding, session persistence, registration persistence, and canonical node metadata so Core no longer has to infer the node API port from the UI origin.
- Task 779 updates `/api/nodes/{node_id}/...` proxy routing to use canonical `api_base_url` metadata, while preserving safe fallback behavior for older registrations that only expose UI metadata.
- Task 780 surfaces canonical node API metadata in the operator/admin UI so onboarding review and node detail pages show the effective node API origin.
- Task 781 updates the onboarding/request schemas and verified docs so the node UI and node API contracts are both explicit and proxy-safe.

## Task 752.1
Original task detail preserved from the queue update added after queue normalization.

- Rework Edge Gateway to enforce single-origin Core routing.
- Target public architecture:
  - `/` -> Core UI on port 80
  - `/api/*` -> Core API on port 9001
  - `/nodes/*` -> node UI proxy on port 9001
  - `/addons/*` -> addon UI proxy on port 9001

Implementation note:

- Completed by switching Edge Gateway and Cloudflare rendering to a single canonical public hostname with reserved Core-owned path roots and path-based ingress routing.

## Task 782-792
Original task details preserved from the Milestone 1 Supervisor planning block requested for `docs/New_tasks.txt`.

Active normalized queue entries:

- Task 782: Define Supervisor-owned runtime models for real Nodes
- Task 783: Add Supervisor runtime registration store for real Nodes
- Task 784: Add Supervisor runtime registration API for real Nodes
- Task 785: Add Supervisor runtime heartbeat API for real Nodes
- Task 786: Add freshness evaluation for Supervisor-managed real Nodes
- Task 787: Expose Supervisor runtime list and detail APIs for real Nodes
- Task 788: Add Supervisor lifecycle action APIs for real Nodes
- Task 789: Keep standalone addon runtime summaries separate from real Node runtime summaries
- Task 790: Add Core read-only integration for Supervisor-owned real Node runtime truth
- Task 791: Add tests for Supervisor real Node registration, heartbeat, and freshness flows
- Task 792: Update Supervisor docs and schemas for the real Node runtime contract

Preserved details:

- The milestone goal is to make Supervisor the first host-local authority that real Nodes talk to for registration, heartbeat, and runtime state, while keeping Core as governance, trust, and orchestration authority.
- Task 782 covers first-class Supervisor-managed real Node models and must keep them separate from compatibility-era standalone addon runtime models. The model set should include node identity, host identity, registration payload, heartbeat payload, runtime status payload, action result payload, and freshness or last-seen metadata.
- Task 783 covers a Supervisor-owned persistence layer for runtime registration and state, separate from Core onboarding registration data. It should store node id, node type, host-local runtime metadata, lifecycle state, heartbeat timestamps, health status, and last error.
- Task 784 covers `POST /api/supervisor/runtimes/register`, including validation, upsert behavior, and normalized Supervisor-owned runtime identity output.
- Task 785 covers `POST /api/supervisor/runtimes/heartbeat`, including updates to last-seen time, health state, runtime state, and optional resource or diagnostic fields, while rejecting heartbeats from unknown nodes.
- Task 786 covers freshness state computation for online, stale, offline, and error conditions, plus configurable timeout defaults and exposure of freshness in Supervisor summaries.
- Task 787 covers `GET /api/supervisor/runtimes` and `GET /api/supervisor/runtimes/{node_id}` so real Node runtimes can be inspected without overloading standalone addon routes.
- Task 788 covers `POST /api/supervisor/runtimes/{node_id}/start`, `stop`, and `restart` for the real Node contract while preserving the existing standalone addon lifecycle routes during transition.
- Task 789 covers explicit separation of real Node runtime summaries from compatibility standalone addon summaries so the Supervisor API no longer treats standalone addon runtimes as if they were real Nodes.
- Task 790 covers read-only Core integration so Core can consume Supervisor-owned runtime truth for real Nodes without moving trust, onboarding approval, governance, capability registry, or scheduling out of Core in this milestone.
- Task 791 covers model validation tests, Supervisor route tests, registration store tests, heartbeat freshness tests, error handling for missing or unregistered nodes, and regression coverage to ensure standalone addon flows continue to work.
- Task 792 covers the minimum documentation and schema updates needed after implementation, specifically in `docs/supervisor/domain-models.md`, `docs/supervisor/runtime-and-supervision.md`, `docs/supervisor/architecture-gap.md`, and relevant schema files under `docs/json_schema/`.

Definition of done preserved from the original planning block:

- A real Node can register with Supervisor.
- A real Node can heartbeat to Supervisor.
- Supervisor can report fresh, stale, or offline runtime state for that Node.
- Core can consume Supervisor runtime truth without taking over host-local runtime ownership.
- Existing standalone addon Supervisor behavior remains functional.

## Task 793-802
Original task details preserved from the request to migrate Supervisor into a separate entity that can run on Core or Node hosts.

Active normalized queue entries:

- Task 793: Define Supervisor service boundary and external API host binding
- Task 794: Add Supervisor standalone API server entrypoint
- Task 795: Add Supervisor service configuration and environment contract
- Task 796: Add Supervisor systemd unit for API service (host-agnostic)
- Task 797: Decouple Core from in-process Supervisor API wiring
- Task 798: Add Supervisor client integration in Core for remote Supervisor hosts
- Task 799: Add health and readiness probes for Supervisor API service
- Task 800: Update deployment scripts for Supervisor API service installation
- Task 801: Add tests for Supervisor API server and remote client integration
- Task 802: Update docs and schemas for Supervisor standalone service

Preserved details:

- The new Supervisor service must run independently of Core and be deployable on any host (Core host or Node host).
- Core should treat Supervisor as an external runtime authority, not an in-process service, once this migration is complete.
- The Supervisor API service should expose the existing `/api/supervisor/*` routes and be able to bind to loopback or a Unix domain socket when configured.
- The migration must preserve compatibility for standalone addon orchestration while enabling remote Supervisor runtimes.
- Deployment and systemd templates must allow Supervisor API services to be installed on non-Core hosts with minimal configuration drift.
- Use a Hexe-named default port for the Supervisor API service with a high likelihood of being available. Default to port `57665` and expose override via `HEXE_SUPERVISOR_PORT`.
- The Supervisor service is backend-only; no Supervisor UI is part of this migration.
- The Core UI will later add a Supervisor section, and that same Core UI will also host remote Supervisor detail pages.
- Use a consistent Unix socket path on every host for local-only access: `/run/hexe/supervisor.sock`.
- The Supervisor runtime ownership target for this migration is:
  - Core runtime when the Supervisor is deployed on the Core host
  - Node runtime processes on any host
  - Aux services and containers declared by Nodes
  - Embedded addons
- Container heartbeats via the Supervisor Unix socket are mandatory for aux services/containers. Each aux container must include a lightweight heartbeat script or sidecar that posts `POST /api/supervisor/runtimes/heartbeat` over `/run/hexe/supervisor.sock`.
## Task 910
Original task details:
- Add node service inventory registration to Supervisor (backend/frontend/node services).
- Expose Supervisor endpoints to fetch node service status and control start/stop/restart.
- Wire Supervisor UI to surface node services when provided.
- Update docs to describe node service inventory and control surfaces.

## Task 911
Original task details:
- Redesign Supervisor UI managed-node runtime section to separate runtime summary vs service monitoring.
- Top-level fields: Name, Node ID, Runtime, Desired State, Runtime State, Health, Actions.
- Remove RPS/P95/Err%/Freshness from runtime row.
- Nested services table: Service, State, Health, CPU, Memory (+ optional pid/uptime/container id if available).
- Keep lifecycle actions available.

## Task 925-931
Original task details preserved from `docs/mqtt/node-domain-event-promotion.md`.

Active normalized queue entries:

- Task 925: Add Core node domain event promoter service
- Task 926: Validate node domain event producer identity and payload schema
- Task 927: Enforce node domain event privacy and payload safety policy
- Task 928: Add node domain event deduplication and noisy-node limiting
- Task 929: Publish accepted node domain events to Core-owned event topics
- Task 930: Record node domain event promotion decisions for operators
- Task 931: Add node domain event promotion tests and verified docs

Preserved details:

- Core should subscribe to `hexe/nodes/+/events/#` and treat node-originated messages as raw domain events that require promotion before shared consumption.
- The promoter must extract `<node_id>` from `hexe/nodes/<node_id>/events/<domain>/<event_name>`.
- The promoter must verify the MQTT principal is an active `synthia_node` linked to the topic node id.
- Retained node-originated event messages must be rejected.
- Node-originated payloads must validate against the node-originated schema. Email-node input events currently reference `HexeEmail/docs/schemas/email-node-domain-event.schema.json`.
- The promoter must verify payload `source.node_id` matches the topic node id.
- The promoter must enforce payload privacy rules and reject or redact forbidden data such as raw email bodies, tokens, API keys, session cookies, verification codes, full payment or bank account numbers, full street addresses without explicit policy, attachments, and large HTML payloads.
- The promoter must enforce noisy-node behavior using initial thresholds from the promotion doc: watch above 60 events/minute or 10 invalid events in 10 minutes; limited above 180 events/minute, 50 invalid events in 10 minutes, or 1 MiB/minute payloads; blocked for sustained limited state, repeated malformed bursts, or suspected secret/raw-body leakage.
- Deduplication should use event id, source topic, and optional subject ids.
- Accepted events must publish to both source-preserving topics `hexe/events/nodes/<node_id>/<domain>/<event_name>` and domain topics `hexe/events/<domain>/<event_name>`.
- Promoted payloads must validate against `docs/json_schema/core_promoted_node_domain_event.schema.json`.
- Promotion accept, reject, limit, redact, dedupe, and noisy-node decisions must be recorded in Core observability.
- Recent noisy-node and promotion decisions should be exposed through an operator API.
- Trusted nodes may subscribe to Core-promoted domain events under `hexe/events/#`, but must not receive broad publish access to `hexe/events/#`.

## Task 932-947
Original task details preserved from the Core-owned node UI migration planning block formerly embedded in `docs/New_tasks.txt`.

Active normalized queue entries:

- Task 932: Discover Core UI runtime and rendered-node migration boundaries
- Task 933: Serve the built Core frontend artifact in production
- Task 934: Add production UI route precedence and SPA fallback tests
- Task 935: Update bootstrap update and backend reload scripts for production UI builds
- Task 936: Replace production systemd wiring for Core UI
- Task 937: Tighten production frontend configuration and same-origin API behavior
- Task 938: Define the Core-owned node UI manifest contract
- Task 939: Define initial Core-owned node card response contracts
- Task 940: Build Core manifest fetch and validation service
- Task 941: Build Core rendered-node UI data loading layer
- Task 942: Build Core renderer registry and first shared card renderers
- Task 943: Build Core manifest-backed node page shell
- Task 944: Build Core node action execution layer
- Task 945: Add pilot rendered-node UI fixtures and integration tests
- Task 946: Add rendered-node UI feature gate and legacy proxied-UI fallback
- Task 947: Update verified docs for production Core UI and rendered-node UI migration

Scope and boundaries:

- Work in the Core repository only.
- Do not implement node-side repository changes from this queue.
- Preserve node-side requirements under `docs/nodes/ui-migration/`.
- Existing node-hosted operational UIs must remain usable until Core-rendered UI reaches feature parity.
- Use existing Core conventions for backend, frontend, scripts, systemd units, tests, and docs.
- Make minimal, production-ready changes in small reviewable units.
- Commit completed implementation work task-by-task when this queue is executed.

Reference docs and code to inspect before implementation:

- `docs/nodes/future-dev/core-rendered-node-ui-migration.md`
- `docs/nodes/ui-migration/README.md`
- `docs/nodes/ui-migration/node-requirements.md`
- `docs/core/frontend/frontend-and-ui.md`
- `docs/core/frontend/proxied-ui-contract.md`
- `docs/core/api/proxied-ui-metadata.md`
- `docs/core/api/proxied-ui-forwarded-headers.md`
- `frontend/package.json`
- `frontend/vite.config.ts`
- `backend/app/main.py`
- `backend/app/nodes/proxy.py`
- `backend/app/addons/proxy.py`
- `backend/app/reverse_proxy.py`
- `scripts/bootstrap.sh`
- `scripts/update.sh`
- `scripts/configure-frontend-api.sh`
- `scripts/reload-backend.sh`
- `systemd/user/hexe-frontend-dev.service.in`
- `systemd/user/hexe-backend.service.in`
- `systemd/user/hexe-dashboard.service.in`

Preserved task details:

- Task 932 discovers the existing Core backend, frontend, auth/session, node proxy, addon proxy, websocket proxy, deployment scripts, and systemd boundaries before changing runtime behavior. Completion requires concise implementation notes or doc updates that cite concrete files and confirm the migration remains Core-only.
- Task 933 adds production serving for the built `frontend/dist` artifact. Completion requires `npm run build` to produce the artifact, Core production runtime to serve it, browser refresh to work on nested Core routes, and `/api/*`, `/nodes/{node_id}/ui/*`, `/addons/{addon_id}/*`, and websocket proxy routes to remain unshadowed by SPA fallback.
- Task 934 adds regression coverage for static asset serving, SPA fallback, and route precedence. Completion requires targeted backend tests proving Core API, node UI proxy, addon UI proxy, and websocket proxy paths still route correctly with production UI hosting enabled.
- Task 935 updates install/update/backend reload flows to install frontend dependencies and run production frontend builds when needed. Completion requires fresh install, update, and the backend reload helper path to rebuild or preserve the built Core UI correctly without requiring the Vite dev server as the production runtime.
- Task 936 replaces production systemd wiring for the Core UI. Completion requires production units not to run `npm run dev`, dashboard/service dependencies to stop depending on `hexe-frontend-dev.service`, and the operator-facing URL to use the production Core UI. Keep a clearly developer-only Vite workflow.
- Task 937 tightens production frontend configuration so production browser API traffic uses relative same-origin paths. Completion requires dev-only CORS origins and Vite proxy behavior to be development-only, while admin session, node proxy, addon proxy, and websocket flows still work from production origin.
- Task 938 defines the canonical Core-owned node UI manifest contract. It must cover `schema_version`, node identity, node type, display name, pages, surfaces, data endpoints, action endpoints, detail endpoint templates, refresh policy, and optional revision. It must reject React components, arbitrary HTML, inline scripts, browser-executable code, secrets, and giant full-page data payloads.
- Task 939 defines initial Core-owned card response contracts for `node_overview`, `health_strip`, `facts_card`, `warning_banner`, `action_panel`, `runtime_service`, and `provider_status`. It must include shared conventions for `updated_at`, tones, empty states, stale data, errors, retry metadata, and confirmation metadata.
- Task 940 builds the Core service/client path that fetches and validates manifests from trusted nodes through existing discovery/service-resolution boundaries. Completion requires tests for successful fetch, unsupported manifest version, validation failure, trust failure, and operator-readable fetch failure.
- Task 941 builds a shared frontend data loading layer for rendered-node cards. It must support lazy visible-card loading, cache keys by node id/surface id/endpoint/revision, request deduplication, manual refresh, stale state, retry state, request cancellation, and visibility-aware polling for `live`, `near_live`, `manual`, `detail`, and `static` modes.
- Task 942 builds the frontend renderer registry and the first shared card renderers: `node_overview`, `health_strip`, `facts_card`, and `warning_banner`. Completion requires loading, success, empty, stale, error, retry, and unsupported-kind states to render without breaking existing proxied node UI.
- Task 943 builds the Core-owned manifest-backed node page shell with navigation, layout, responsive behavior, page selection, card placement, and refresh controls. Completion requires a Core route to render a manifest-backed node page without using a node-hosted React app while the legacy proxied node UI remains available.
- Task 944 builds Core-controlled action execution for manifest-declared node actions. It must support method, endpoint, request metadata, confirmation metadata, success state, error state, and audit logging. Node endpoints remain authoritative for authorization and validation, and destructive or sensitive actions require confirmation metadata.
- Task 945 adds a static Voice-like or Email-like pilot fixture with overview, health, warnings, runtime, one domain page, one action, and one refresh policy. Completion requires integration tests for manifest fetch, validation, rendering, card data loading, refresh, and action execution using fake node endpoints, without requiring a real node repository.
- Task 946 adds a feature gate for Core-rendered node UI and a fallback path to the current proxied node UI. Completion requires operators to opt into Core-rendered node UI per environment or node and disabling the feature to return operators to the existing proxied UI path.
- Task 947 updates verified docs after implementation only. It must update Core frontend/API docs and node migration handoff docs to reflect implemented behavior, link canonical Core contracts from `docs/nodes/ui-migration/node-requirements.md`, and avoid documenting planned behavior as implemented.

Definition of done preserved from the original planning block:

- Core production UI no longer depends on the Vite dev server.
- Core serves the built UI without breaking API, node proxy, addon proxy, or websocket routes.
- Backend reload/rebuild helper scripts do not leave production Core serving stale or missing UI assets.
- Core owns rendered node UI layout, cards, data loading, refresh behavior, actions, and operator states.
- Nodes provide manifests, data endpoints, detail endpoints, and action endpoints only.
- Node-local UI remains available for setup, recovery, diagnostics, and migration fallback.
- The first pilot can render useful node operational UI in Core without requiring node repository changes in this queue.

## Task 954
Original task details:
- Consolidate duplicated documentation from `core/docs` and `supervisor/docs` into one root-level `docs/` source of truth.
- Preserve current Core documentation content as the primary source unless supervisor-only content exists only under `supervisor/docs`.
- Remove or replace mirrored `core/docs` and `supervisor/docs` so future edits happen in the root docs tree.
- Update repository links and README references so readers land in root `docs/`.
- Preserve task workflow state by moving the normalized task queue and completed-task record into root `docs/`.
- Acceptance: root `docs/` exists, duplicate docs trees are removed or reduced to pointers, active docs links resolve, and the repository validates with targeted docs/link checks.

## Task 955
Original task details:
- Goal: Reduce `backend/app/api/system.py` from a single large mixed-domain router into smaller routers with no behavior changes.
- Scope: Move node onboarding, reauth, registrations, trust, governance, budgets, service resolution, provider routing, telemetry, and addon-runtime endpoints into domain-specific router modules.
- Scope: Preserve all current public endpoint paths, auth behavior, request schemas, response shapes, and legacy hidden routes where still required.
- Scope: Keep `build_system_router` or an equivalent composition entrypoint small and explicit.
- Acceptance: Existing backend tests pass for Core and Supervisor mirrors.
- Acceptance: OpenAPI route list is unchanged except for intentionally documented internal implementation grouping.
- Acceptance: Docs or architecture notes identify the new router ownership boundaries.

## Task 956
Original task details:
- Goal: Reduce `backend/app/system/mqtt/router.py` into maintainable subrouters without changing MQTT behavior.
- Scope: Separate setup/runtime lifecycle endpoints from debug publish/subscribe endpoints.
- Scope: Separate principal/user management, bridge grants, runtime health, observability, and provisioning endpoints.
- Scope: Preserve existing route paths, aliases, response shapes, and admin/session requirements.
- Acceptance: MQTT backend tests pass in Core and Supervisor mirrors.
- Acceptance: Live `/api/system/mqtt/status` and `/api/system/mqtt/runtime/health` still report correctly.
- Acceptance: No route path regressions in generated OpenAPI.

## Task 957
Original task details:
- Goal: Reduce `backend/app/store/router.py` into focused units while keeping store behavior stable.
- Scope: Extract catalog/source management, install/update/uninstall, standalone desired-state, status/diagnostics, and audit endpoints.
- Scope: Keep signing, artifact verification, and catalog resolution logic behind clearly named service helpers.
- Scope: Preserve install-session behavior and all public API paths.
- Acceptance: Store backend tests pass in Core and Supervisor mirrors.
- Acceptance: Existing addon install/update/uninstall flows still work against the same endpoints.
- Acceptance: Router modules have clear domain ownership and limited cross-imports.

## Task 958
Original task details:
- Goal: Prevent accidental drift between mirrored Core and Supervisor source trees.
- Scope: Define the set of files or directories that must remain identical across `core/` and `supervisor/`.
- Scope: Add a script that compares those mirrored paths and reports exact mismatches.
- Scope: Add a backend or repository-level test/CI check that fails when mirrored files drift unexpectedly.
- Acceptance: Running the drift check on a clean tree passes.
- Acceptance: Intentional mirror exceptions are documented in one place.
- Acceptance: The check covers backend, frontend, docs, scripts, and systemd mirror areas as appropriate.

## Task 959
Original task details:
- Goal: Make Core runtime configuration discoverable and keep env-var docs aligned with code.
- Scope: Inventory active `HEXE_*`, `MQTT_*`, `STORE_*`, and compatibility `SYNTHIA_*` environment variables used by Core runtime code and scripts.
- Scope: Introduce a structured config registry or generated manifest for env names, defaults, owners, sensitivity, and docs text.
- Scope: Generate or update operator documentation from that registry where practical.
- Acceptance: Config docs cover backend, supervisor, MQTT, Cloudflared, store, auth, frontend serving, and node onboarding settings.
- Acceptance: Sensitive values are clearly marked and are not logged or exposed.
- Acceptance: Tests or validation catch undocumented new env vars.

## Task 960
Original task details:
- Goal: Keep live runtime state ignored while preserving default catalog-source bootstrap behavior.
- Scope: Move tracked `var/store_sources.json` defaults into a template or config defaults location outside live runtime state.
- Scope: Update store source loading to initialize missing live state from the template/defaults.
- Scope: Preserve current official catalog source behavior for fresh installs.
- Acceptance: `core/var/` and `supervisor/var/` contain no tracked live runtime state files.
- Acceptance: Fresh install/bootstrap still creates or reads the official catalog source.
- Acceptance: Existing store source tests pass and include missing-state initialization coverage.

## Task 961
Original task details:
- Goal: Catch accidental API drift, especially removed job/scheduler endpoints.
- Scope: Generate a deterministic OpenAPI route/path snapshot for Core.
- Scope: Add regression checks proving removed job queue, job lease, worker, per-job budget usage-report, and scheduler jobs endpoints are absent.
- Scope: Include a documented update workflow for intentional API changes.
- Acceptance: Snapshot test passes in Core and Supervisor mirrors.
- Acceptance: The test fails if `/api/system/scheduler/jobs`, job lease routes, worker routes, or per-job budget usage-report routes reappear.
- Acceptance: API reference docs are updated when intentional route changes occur.

## Task 962
Original task details:
- Goal: Reduce documentation drift now that Core no longer handles jobs.
- Scope: Classify active docs, archive docs, migration notes, temp AI-node docs, future-dev docs, and screenshots.
- Scope: Move or clearly mark stale scheduler/job/worker material that remains only as historical context.
- Scope: Fix obvious typos in active doc paths and headings, including `ui-migration` if still active.
- Acceptance: Active docs no longer imply Core owns job queueing, job leasing, worker execution, or scheduler orchestration.
- Acceptance: Historical docs are clearly separated from active source-of-truth docs.
- Acceptance: Documentation index pages route readers to current Core, Supervisor, MQTT, Node, and Addon contracts.

## Task 963
Original task details:
- Goal: Reduce CPU and latency on the Settings / Supervisor page while preserving host and runtime observability.
- Issue: Supervisor resource history SQLite grew large enough that synchronous prune/query work and 10-second UI polling caused high `hexe-supervisor-api.service` CPU.
- Scope: Add timestamp indexes for resource history pruning, throttle prune frequency, and reduce Supervisor UI history polling/window size.
- Acceptance: Resource history store tests pass, frontend builds, Supervisor history endpoints respond faster after restart, and the hot Supervisor API CPU drops under normal dashboard viewing.

## Task 964
Original task details:
- Goal: Add explicit operational maintenance controls for Supervisor resource history storage.
- Scope: Provide a safe checkpoint/vacuum or rotation workflow for `supervisor_resource_history.sqlite3`, document retention/prune interval env vars, and expose DB size/count visibility where useful.
- Acceptance: Operators can compact or rotate the history DB without losing current service health, and maintenance docs explain when to use it.

## Task 965
Original task details:
- Goal: Prevent stale Supervisor fleet records and duplicate UI history requests from confusing operators.
- Scope: Review stale/offline fleet record retention, identify duplicate local/remote history calls on the Supervisor page, and ensure old supervisors are clearly hidden, pruned, or marked as historical.
- Acceptance: The Supervisor page no longer shows long-dead records as peers by default, and each visible supervisor/runtime history is fetched once per refresh cycle.

## Task 966
Original task details:
- Audit finding addressed: Store verification is documented as enforced, but `core/backend/app/store/signing.py` currently disables checksum and signature checks.
- Inspect the active addon/store standards and the current store install/update flow before editing.
- Prefer implementing real artifact SHA-256 and detached signature verification in Core and the Supervisor mirror.
- If full verification cannot be completed safely in one task, update the active docs and operator-facing status so they no longer claim enforced verification, and create a follow-up task with the exact blocker.
- Ensure invalid checksum, invalid signature, missing publisher key, and valid artifact paths have focused tests.
- Preserve Core/Supervisor mirror alignment.
- Verification: Run targeted store signing/install tests for Core and Supervisor.
- Verification: Run `python tools/check_mirror_drift.py`.

## Task 967
Original task details:
- Audit finding addressed: FastAPI emits duplicate OpenAPI operation-id warnings for addon/node proxy routes, while the snapshot tool suppresses warnings.
- Inspect proxy route registration in `core/backend/app/addons/proxy.py` and `core/backend/app/nodes/proxy.py`.
- Add explicit unique operation IDs or exclude catch-all proxy routes from OpenAPI where that is the cleaner contract.
- Update `tools/update_openapi_snapshot.py` so duplicate OpenAPI operation-id warnings fail the check instead of being hidden.
- Mirror changes into Supervisor.
- Verification: Run `python tools/update_openapi_snapshot.py --check`.
- Verification: Run Core and Supervisor OpenAPI snapshot tests.
- Verification: Run `python tools/check_mirror_drift.py`.

## Task 968
Original task details:
- Audit finding addressed: mirror, env registry, and OpenAPI guards exist, but there is no single operator/developer command that runs the Core/Supervisor health checks together.
- Add a lightweight repo-level health script or documented command that runs:
  - `python tools/check_mirror_drift.py`
  - `python tools/check_env_registry.py --check-docs`
  - `python tools/update_openapi_snapshot.py --check`
  - targeted Core/Supervisor backend tests where practical
- Document the command in the active developer/operator entrypoint.
- Keep the command safe for local development and avoid requiring unrelated nodes.
- Verification: Run the new health entrypoint.
- Verification: Run any touched documentation or script checks.

## Task 969
Original task details:
- Audit finding addressed: ignored local runtime/build folders can remain in the repo tree and confuse source audits even though tracked source is clean.
- Add a dry-run-first helper that reports ignored local artifacts such as `node_modules`, `dist`, `.venv`, `.pytest_cache`, `logs`, `data`, `runtime`, `temp`, and `var` under Core/Supervisor.
- Do not delete anything by default.
- Make the helper explain which directories are source-owned versus runtime/build/cache artifacts.
- Document the helper in the active development or operator docs.
- Verification: Run the helper in report/dry-run mode.
- Verification: Confirm `git status --short` remains clean except for intentional task changes.
- Queue stop marker: `[STOP HERE]` follows Task 969 so the audit/guardrail cleanup batch can be reviewed before telemetry/history and Supervisor Fleet behavior work begins.

## Task 970
Original task details:
- User-observed gap addressed: The Supervisor UI shows Core Services & Aux Runtimes values, but Core/Supervisor must record those values as structured telemetry instead of treating them as display-only snapshots.
- Inspect the current Core Services & Aux Runtimes data source, API response models, and Supervisor resource history storage before editing.
- Record these fields per service/runtime sample: `name`, `id`, `kind`, `mode`, `state`, `health`, `desired`, `rps`, `p95_ms`, `err_percent`, `cpu_percent`, `mem_percent`, `reported_at`, and source host/supervisor identity.
- Preserve distinction between Core services and aux runtimes such as `cloudflared`.
- Store `unknown` and missing metric values explicitly enough that operators can tell "not reported" from zero.
- Add retention or pruning behavior consistent with existing Supervisor resource history controls.
- Preserve Core/Supervisor mirror alignment.
- Verification: Add or update backend tests that create service/runtime samples and verify the persisted fields.
- Verification: Run targeted Supervisor/Core resource-history tests.
- Verification: Run `python tools/check_mirror_drift.py`.

## Task 971
Original task details:
- User-observed gap addressed: Operators need to confirm that the table values are being recorded and can be inspected over time.
- Expose the recorded Core Services & Aux Runtimes samples through a documented API or extend the existing resource history API if that is the local pattern.
- Update the Supervisor UI so current table rows can be traced to recorded samples, with clear handling for unknown state/health and missing RPS/P95/ERR metrics.
- Add a lightweight history/detail view or diagnostics affordance for service/runtime rows where appropriate.
- Update active Supervisor/Core documentation to describe the recorded fields and retention behavior.
- Preserve Core/Supervisor mirror alignment.
- Verification: Run targeted backend API tests for the recorded-history endpoint or extended payload.
- Verification: Run targeted frontend tests/build checks for the Supervisor page.
- Verification: Run `python tools/update_openapi_snapshot.py --check` if API paths or methods change.
- Verification: Run `python tools/check_mirror_drift.py`.

## Task 972
Original task details:
- User-observed gap addressed: The Supervisor Fleet table can show the primary `Hexe` supervisor as `Offline` while still reporting `Health=Ok`, nodes, runtimes, CPU, memory, and an old `Last seen` timestamp.
- Inspect the Supervisor fleet heartbeat ingestion, freshness classification, stale-record retention, and local supervisor identity matching.
- Determine whether the `Hexe` row is a legacy duplicate, stale local identity, missed heartbeat, or display merge issue.
- Ensure stale/offline records do not keep misleading live-looking resource counts unless they are clearly marked as last-known values.
- Add or update backend tests covering stale supervisor records, duplicate supervisor identities, and offline freshness transitions.
- Preserve Core/Supervisor mirror alignment.
- Verification: Run targeted Supervisor fleet/heartbeat/resource summary tests.
- Verification: Run `python tools/check_mirror_drift.py`.

## Task 973
Original task details:
- User-observed gap addressed: Operators need the Supervisor Fleet view to explain why `Hexe` is offline and whether displayed metrics are current or last-known.
- Update the Supervisor Fleet UI so freshness, health, last-seen age, and last-known resource metrics cannot imply a stale host is currently healthy.
- Add a row-level diagnostic affordance or detail payload showing heartbeat source, supervisor id, host id, freshness threshold, last heartbeat age, and reason for offline classification.
- Clearly distinguish `Online`, `Stale`, `Offline`, and `Unknown` states in labels and tones.
- Update active Supervisor docs with the fleet freshness and health semantics.
- Preserve Core/Supervisor mirror alignment.
- Verification: Run targeted frontend tests/build checks for the Supervisor Fleet view.
- Verification: Run targeted backend tests for any new diagnostic payload.
- Verification: Run `python tools/update_openapi_snapshot.py --check` if API paths or methods change.
- Verification: Run `python tools/check_mirror_drift.py`.

## Task 974
Original task details:
- Goal: Redesign the node capability declaration protocol so a node does not need to claim it can perform a task merely to request that task from another node.
- Preserve compatibility with current v1 declarations while introducing explicit provider-side and requester-side fields.
- Treat provider capabilities as tasks the declaring node can execute for others.
- Treat requested task families or service dependencies as tasks the declaring node is allowed or expected to consume from other nodes.
- Keep `declared_task_families` and `declared_capabilities` as compatibility aliases for provider-side capabilities in existing v1 manifests.
- Add new manifest fields such as `provided_task_families` and `requested_task_families`, or choose clearer names if the existing codebase already has a better local convention.
- Do not require `requested_task_families` to match `provided_task_families`.
- Continue validating task-family syntax and provider identifiers.
- Update capability manifest validation in both Core and Supervisor mirrors.
- Update capability acceptance/profile persistence so provider-side capabilities and requester-side dependencies are stored distinctly.
- Update registration persistence/API payloads to expose both concepts without breaking current clients.
- Update schema docs and generated JSON schema artifacts that describe node capability declarations, responses, profiles, registrations, and resolution models.
- Preserve Core/Supervisor mirror alignment.
- Acceptance: Existing v1 declarations using only `declared_task_families` still validate and behave as provider capability declarations.
- Acceptance: A new declaration can include provider capabilities that differ from requested task families.
- Acceptance: Capability endpoints remain tied only to provider-side capabilities, not requester-side dependencies.
- Acceptance: Tests pass in both Core and Supervisor where mirrored.
- Verification: Run focused capability manifest, capability declaration, capability profile, registration, governance, and mirror drift tests.
- Verification: Run `python tools/check_mirror_drift.py`.

## Task 975
Original task details:
- Goal: Change task resolution governance so requester eligibility is based on the node's requested task families or service dependencies, not on the tasks the node provides.
- `routing_policy_constraints.allowed_task_families` must be derived from requester-side task dependencies when present.
- Provider-side task declarations must remain available for provider discovery and execution endpoint publication.
- If a legacy node has no requester-side field, keep existing behavior only as a compatibility fallback.
- Keep provider/model governance constraints intact.
- Preserve budget-policy integration and provider-owned budget behavior for delegated resolution.
- Update governance bundle generation in both Core and Supervisor mirrors.
- Update service resolution so the initial requester gate uses requester-side allowed tasks.
- Keep candidate discovery filtering against provider-side capabilities.
- Update audit details only if needed to clarify requester task authorization versus provider capability matching.
- Acceptance: A voice node that provides only voice capabilities but requests `task.chat` can resolve an AI-node candidate for `task.chat`.
- Acceptance: A node without `task.chat` in requester-side dependencies cannot resolve `task.chat` unless legacy fallback intentionally applies.
- Acceptance: Candidate nodes are still selected only when they provide the requested task family.
- Acceptance: Provider-owned budget checks still use the provider node budget when a delegating/requesting node resolves another node's service.
- Verification: Add or update focused tests in `test_node_service_resolution_api.py` for the Voice-to-AI `task.chat` case.
- Verification: Add a negative test for an unauthorized requester task family.
- Verification: Run focused service resolution and node budget tests.
- Verification: Run `python tools/check_mirror_drift.py`.

## Task 976
Original task details:
- Goal: Make the protocol change safe for current persisted registrations, capability profiles, governance bundles, and runtime data.
- Existing nodes must continue to load from current JSON stores.
- Existing provider-capability data must not be lost.
- New requester-side dependency fields should default safely for legacy records.
- Governance regeneration should produce the new routing constraints without requiring manual JSON edits.
- Add load-time defaults or schema-version migration for node registrations and capability profiles.
- Decide whether persisted governance bundles need lazy compatibility handling, forced regeneration, or an explicit migration utility.
- Document the chosen migration path in the relevant node/Core docs.
- Do not edit live runtime data files as the primary fix unless a migration task explicitly requires it.
- Acceptance: Current `hexevoice` registration can remain a provider of voice/intent/TTS capabilities while gaining requester permission for `task.chat` through the new protocol.
- Acceptance: Current AI-node registration remains the provider for `task.chat`.
- Acceptance: Old store records load without exceptions and keep their previous API shape where compatibility requires it.
- Acceptance: New store records include distinct provider and requester capability/dependency fields.
- Verification: Run focused store/profile/governance loading tests.
- Verification: Run service resolution regression tests with legacy and new-style records.
- Verification: Run `python tools/check_mirror_drift.py`.

## Task 977
Original task details:
- Goal: Make the new protocol explicit so future node implementations do not repeat the old inversion.
- Define provider-side capabilities as what a node can execute for others.
- Define requester-side dependencies as what a node may request from other providers.
- Define provider access/model metadata as which external provider/model choices back a provider node.
- Update node capability lifecycle docs, capability taxonomy docs, budget/service-resolution docs, and schema docs.
- Add the Voice-to-AI `task.chat` example: HexeVoice provides voice/intent/TTS capabilities, HexeVoice requests `task.chat`, AI node provides `task.chat`, and Core resolves the AI-node candidate without Voice declaring itself as a chat provider.
- Acceptance: Docs no longer imply that `declared_task_families` is the correct way for a consuming node to request delegated service execution.
- Acceptance: Service-resolution docs clearly state that requester authorization and provider capability matching are separate checks.
- Acceptance: Schema docs and examples match implemented runtime behavior.
- Verification: Run documentation/schema checks available in the repo.
- Verification: Run `python tools/check_repo_health.py --skip-backend-tests` if the full health check is too expensive.
- Verification: Run `python tools/check_mirror_drift.py`.

## Task 978
Original task details:
- Source finding: Provider/model governance filters are documented more strongly than code enforces.
- Goal: Decide and implement the intended enforcement semantics for `routing_policy_constraints.allowed_providers` and `routing_policy_constraints.allowed_models` during node service resolution and authorization.
- Current code evidence: `core/backend/app/system/onboarding/governance.py` emits `allowed_providers`, `allowed_models`, and `allowed_task_families`; `core/backend/app/system/services/node_resolution.py` enforces `allowed_task_families` directly and filters provider/model only through request preference and candidate model availability.
- Documentation evidence: `docs/core/node-service-resolution-and-budgeting.md` says governance allowed providers and models filter candidates, while `docs/core/node-budget-assignment-flow.md` says only `allowed_task_families` is enforced directly in `resolve_for_node(...)`.
- [STOP] Before changing behavior, confirm whether provider/model fields are mandatory enforcement gates or advisory policy carried in governance.
- If enforcement is confirmed, update `NodeServiceResolutionService` so candidates outside `allowed_providers` or provider-specific `allowed_models` are rejected.
- If advisory semantics are chosen, update docs to clearly say these fields are not resolver gates and identify where they are enforced, if anywhere.
- Preserve the provider/requester split: requester authorization uses `requested_task_families[]`; provider candidate matching uses provider-side capabilities such as `provided_task_families[]`.
- Preserve delegated provider-owned budget checks.
- Apply mirrored implementation/test changes to both Core and Supervisor trees if code changes touch mirrored files.
- Acceptance: A requester cannot resolve or authorize a candidate whose provider is excluded by active governance policy when provider enforcement is enabled.
- Acceptance: A requester cannot resolve or authorize a candidate whose selected model is excluded by active provider model policy when model enforcement is enabled.
- Acceptance: Existing Voice-to-AI `task.chat` delegated resolution still works when the AI provider/model is allowed.
- Acceptance: Docs describe the implemented semantics without contradiction.
- Verification: Run focused node service resolution tests, provider model policy tests, and governance tests.
- Verification: Run `python tools/update_openapi_snapshot.py --check` if API behavior or schema exposure changes.
- Verification: Run `python tools/check_mirror_drift.py`.

## Task 979
Original task details:
- Source finding: Supervisor route ownership is unclear.
- Goal: Clarify the implementation and documentation boundary between Core-hosted Supervisor fleet/status routes and the standalone Supervisor API routes.
- Code evidence: `core/backend/app/supervisor/server.py` creates the standalone Supervisor FastAPI app and mounts `build_supervisor_router(...)` under `/api`; `core/systemd/user/hexe-supervisor-api.service.in` launches `python -m app.supervisor.server`; Core `create_app()` mounts `/api/system/supervisor*` and `/api/system/supervisors*` routes but does not expose `/api/supervisor/health` in the Core OpenAPI snapshot.
- Documentation evidence: `docs/architecture.md` says the migration foundation routes are mounted in `backend/app/main.py`; `docs/supervisor/README.md` says Supervisor API routes are served by the standalone Supervisor service rather than Core.
- Update `docs/architecture.md`, `docs/supervisor/README.md`, and related API docs so they distinguish route host/process ownership.
- If code still exposes an obsolete or misleading Core route wrapper, either remove it safely or document why it remains.
- Acceptance: Docs clearly separate `/api/supervisor/*` standalone Supervisor API routes from `/api/system/supervisor*` and `/api/system/supervisors*` Core routes.
- Acceptance: OpenAPI snapshot expectations match the documented Core route surface.
- Verification: Run `python tools/update_openapi_snapshot.py --check`.
- Verification: Run Supervisor API focused tests if route behavior changes.
- Verification: Run `python tools/check_mirror_drift.py`.

## Task 980
Original task details:
- Source finding: Stale paths and broken documentation links remain in active docs.
- Goal: Repair stale repo paths and broken internal documentation links in active source-of-truth docs.
- Evidence from audit: A Markdown link scan found 146 missing internal or absolute doc links; examples include old `/home/dan/Projects/Hexe/...` anchors and stale `core/backend/synthia_supervisor/` references in `README.md`.
- Preserve historical migration documents when references are explicitly historical.
- Convert active personal absolute paths to repo-relative links.
- Update stale package/path names where the current repository uses `hexe_supervisor` instead of `synthia_supervisor`.
- Add or document a targeted link validation command so future docs changes can catch broken links.
- Acceptance: Active docs no longer send readers to missing local absolute paths for current code.
- Acceptance: Historical/archive references remain clearly marked as historical if retained.
- Acceptance: Link validation for active docs has an executable command or script.
- Verification: Run the new or selected Markdown link validation.
- Verification: Run `python tools/check_repo_health.py --skip-backend-tests` if appropriate.

## Task 981
Original task details:
- Source finding: The hand-written API reference is incomplete beside the generated route snapshot.
- Goal: Make API reference coverage match the generated OpenAPI path snapshot while keeping dynamic proxy routes documented separately.
- Evidence from audit: `docs/core/api/openapi-paths.snapshot.json` contains 223 generated paths; exact comparison against `docs/core/api/api-reference.md` found 119 snapshot paths not listed exactly.
- Keep `docs/core/api/openapi-paths.snapshot.json` as the deterministic machine route contract.
- Add a generated or semi-generated route appendix from the snapshot, or update the API reference so generated routes are discoverable without manual drift.
- Add a separate section for runtime proxy surfaces intentionally excluded from OpenAPI, including node UI/API proxy paths and addon proxy catch-alls.
- Do not treat dynamic proxy catch-alls as stable generated-client operations unless the implementation changes to support that.
- Acceptance: Every generated OpenAPI path is either listed directly or covered by a generated appendix.
- Acceptance: Dynamic proxy route documentation explains why those routes are not in the snapshot.
- Verification: Run `python tools/update_openapi_snapshot.py --check`.
- Verification: Run route/link documentation validation added by this task or Task 980.

## Task 982
Original task details:
- Source finding: Environment docs miss variables read through helper functions and shell helper wrappers.
- Goal: Extend environment registry validation so helper-read variables are scanned and documented.
- Evidence from audit: `tools/check_env_registry.py` passes today but supplemental scanning found helper-read variables missing from `docs/config/core-env-registry.json`, including `HEXE_NODE_PROXY_TIMEOUT_SECONDS`, `HEXE_NODE_UI_HEALTH_TIMEOUT_SECONDS`, `HEXE_SUPERVISOR_CORE_TOKEN`, `HEXE_SUPERVISOR_REPORT_TIMEOUT_S`, `STORE_CATALOG_TIMEOUT_S`, and related Supervisor/addon proxy/runtime variables.
- Update `tools/check_env_registry.py` to scan helper patterns such as `_env_*("NAME")`, `hexe_env NAME`, and `write_env_if_set "NAME"`.
- Add registry entries for active env vars discovered by the improved scanner.
- Regenerate `docs/config/environment.md` from the registry.
- Mark sensitive token/secret values correctly.
- [STOP] After this task, review the expanded registry before broad doc consolidation so stale or intentionally private variables are not documented incorrectly.
- Acceptance: `python tools/check_env_registry.py --check-docs` passes with the expanded scan.
- Acceptance: New registry entries have owners, defaults, descriptions, and sensitivity flags.
- Verification: Run `python tools/check_env_registry.py --write-docs`.
- Verification: Run `python tools/check_env_registry.py --check-docs`.

## Task 983
Original task details:
- Source finding: Duplicate `supervisor/docs/` remains even though root `docs/` is the canonical documentation tree.
- Goal: Consolidate or pointerize duplicate Supervisor documentation so future edits happen in root `docs/`.
- Evidence: `docs/documentation-map.md` says root `docs/` is canonical; `supervisor/docs/` still contains task files, archive docs, reports, and completed/Reasoning files.
- Preserve any supervisor-only content that is not already represented under root `docs/`.
- Replace duplicate active docs with a pointer to the root documentation tree, or archive them if the repository convention supports it.
- Do not delete user-owned operational notes without confirming ownership.
- Update links that still point to `supervisor/docs/` as an active source.
- Acceptance: Root `docs/` remains the single active source of truth.
- Acceptance: `supervisor/docs/` is either removed, reduced to pointers, or clearly classified as archive-only.
- Acceptance: No active task workflow state is stranded under `supervisor/docs/`.
- Verification: Run Markdown link validation.
- Verification: Run `python tools/check_mirror_drift.py` if mirrored files are affected.

## Task 984
Original task details:
- Source finding: Schema docs point at wrong locations.
- Goal: Repair schema documentation links and ownership descriptions.
- Evidence: `docs/core/api/data-and-state.md` links `./desired.schema.json`, `./runtime.schema.json`, and `./addon-manifest.schema.json`, but current schema catalogs live under `docs/json_schema/` and historical standalone-addon schemas live under `docs/addons/standalone-archive/`.
- Update schema links so current Core-owned schemas point to `docs/json_schema/`.
- Keep historical SSAP schema links under `docs/addons/standalone-archive/` clearly marked as historical when applicable.
- Ensure `docs/json_schema/README.md` and `docs/core/api/data-and-state.md` agree on schema ownership.
- Acceptance: Schema links resolve and make current-vs-historical ownership clear.
- Acceptance: Core-owned schema references do not point at missing files.
- Verification: Run Markdown link validation.
- Verification: Run `python tools/update_openapi_snapshot.py --check` if route/schema docs mention generated API shape.

## Task 985
Original task details:
- Source finding: Bluetooth hardware is detected and advertised by Supervisor, but nodes do not have an implemented Core-governed request path for Bluetooth access.
- Goal: Add a Core-owned hardware access request and lease protocol so nodes can request host hardware such as Bluetooth without directly claiming or probing host devices.
- Current code evidence: `core/backend/app/supervisor/service.py` reports `bluetooth_present`, `bluetooth_powered`, `bluetooth_ensure_powered`, `bluetooth_power_error`, and `bluetooth_adapters`; `core/backend/app/supervisor/server.py` and `core/backend/app/system/supervisors.py` advertise `bluetooth` and `bluetooth_governance` when hardware is present.
- Current configuration evidence: `HEXE_BLUETOOTH_ACCESS_POLICY` supports `disabled`, `ask`, `trusted_only`, and `allowed`; `core/scripts/hexe.env.example` says Bluetooth access remains disabled until Core policy grants it.
- Missing behavior: There is no node-facing endpoint, grant/lease model, approval lifecycle, audit trail, or enforcement token that lets a node request and receive governed Bluetooth access.
- [STOP] Before implementation, confirm the intended policy semantics for `disabled`, `ask`, `trusted_only`, and `allowed`, including whether `ask` requires operator UI approval or a pending request state only.
- Add Core data models for hardware resources, access requests, decisions, leases, expiry, revocation, and audit metadata.
- Add node-authenticated Core API routes for requesting hardware access, listing request/lease status, and releasing or canceling leases.
- Add admin/operator API routes for reviewing pending hardware access requests when policy requires approval.
- Ensure Core selects only Supervisor-reported resources and denies requests when no online Supervisor reports the requested hardware capability.
- Tie requester eligibility to node trust, identity, capability/dependency declarations, and existing governance patterns rather than allowing arbitrary node claims.
- Keep Bluetooth as the first resource type, but structure the protocol so later hardware classes such as USB, GPU, camera, or audio devices can reuse it.
- Do not grant OS/device access directly from Core; Core should issue policy decisions and leases that Supervisor enforces locally.
- Preserve Core/Supervisor mirror alignment.
- Acceptance: A node can submit a Bluetooth access request through Core and receive a deterministic `denied`, `pending`, or `granted` response based on policy and Supervisor resource state.
- Acceptance: Requests fail closed when Bluetooth is absent, the reporting Supervisor is stale/offline, the node is not authorized, or policy is `disabled`.
- Acceptance: Granted responses include a short-lived lease identity, target Supervisor/resource identity, expiry, and enough information for the node to call the Supervisor enforcement path without exposing unrelated host hardware.
- Acceptance: Request, grant, release, expiry, and denial events are auditable.
- Verification: Add focused Core API/model tests for disabled, ask/pending, trusted-only, allowed, stale Supervisor, absent Bluetooth, and lease expiry cases.
- Verification: Run `python tools/update_openapi_snapshot.py --check` if API paths or schemas change.
- Verification: Run `python tools/check_mirror_drift.py`.

## Task 986
Original task details:
- Source finding: Supervisor can detect and optionally power Bluetooth adapters, but it does not currently enforce a Core-issued lease or expose a safe node access broker for Bluetooth operations.
- Goal: Implement the Supervisor-side Bluetooth access broker and local enforcement path for Core-issued hardware leases.
- Current code evidence: `core/backend/app/supervisor/service.py` reads `/sys/class/bluetooth`, uses `hciconfig` for adapter details, and may run `bluetoothctl power on`; it only returns resource summaries today.
- Missing behavior: There is no Supervisor endpoint or local service that validates Core-issued leases, scopes Bluetooth operations to an authorized node, or prevents direct unaudited host access.
- [STOP] Before enabling access, choose and document the enforcement mechanism: BlueZ/DBus proxy, Supervisor-mediated command API, container/device permission handoff, or another explicit local mechanism.
- Prefer a Supervisor-mediated API for initial Bluetooth access unless there is a stronger local pattern already present, because it keeps audit, authorization, and host permissions under Supervisor control.
- Add Supervisor APIs that validate Core lease material and expose only the Bluetooth operations required by the requesting node.
- Ensure Supervisor refuses expired, revoked, malformed, wrong-node, wrong-resource, or wrong-Supervisor leases.
- Keep adapter power management separate from access authorization: detecting or powering Bluetooth must not imply a node has access.
- Add local audit events for lease validation, operation attempts, denials, and release/expiry handling.
- Avoid broad host exposure such as giving nodes unrestricted `/var/run/dbus`, `/sys/class/bluetooth`, privileged containers, or raw host Bluetooth command execution unless the confirmed enforcement mechanism explicitly requires and constrains it.
- Preserve existing host resource reporting behavior and current Supervisor UI display.
- Preserve Core/Supervisor mirror alignment.
- Acceptance: Supervisor can validate a Core-issued Bluetooth lease and deny all operations without a valid lease.
- Acceptance: A node with a valid lease can perform only the approved Bluetooth operation surface.
- Acceptance: Expired or revoked leases stop working without requiring a Supervisor restart.
- Acceptance: Bluetooth reporting still works when access policy is disabled.
- Verification: Add focused Supervisor tests for lease validation, denied access, valid access, expiry/revocation, and adapter-unavailable cases.
- Verification: Run targeted Supervisor resource and API tests.
- Verification: Run `python tools/check_mirror_drift.py`.

## Task 987
Original task details:
- Source finding: Current docs/config explain Bluetooth reporting policy, but they do not show how a node requests access because the request flow is not implemented.
- Goal: Document and verify the complete node Bluetooth access flow after Tasks 985 and 986 provide the Core and Supervisor implementation.
- Update node capability/service-resolution docs to distinguish provider capabilities, requester dependencies, and host hardware access requests.
- Update Supervisor docs to describe hardware reporting versus hardware access enforcement, including the fact that `bluetooth_present=true` is not permission to use Bluetooth.
- Update API reference/OpenAPI docs for Core hardware request routes and Supervisor broker routes.
- Add a node-author example showing the expected request sequence: discover eligible Supervisor/resource through Core, request Bluetooth access, handle `denied`/`pending`/`granted`, use the Supervisor broker with the lease, then release or allow expiry.
- Add UI/operator docs for reviewing `ask` policy requests if operator approval is implemented.
- Update environment registry/docs so `HEXE_BLUETOOTH_ACCESS_POLICY`, `HEXE_BLUETOOTH_ENSURE_POWERED`, and `HEXE_BLUETOOTH_POWER_RETRY_S` are all documented with accurate ownership, defaults, and security implications.
- Add or update frontend display only if the current Supervisor/Fleet UI needs to show pending/granted/denied hardware requests, not merely static Bluetooth presence.
- Acceptance: Docs tell node authors exactly how to request Bluetooth access without requiring direct host-device access.
- Acceptance: Operator docs explain who owns policy, approval, lease revocation, and local enforcement.
- Acceptance: API docs and examples match the implemented request/lease/enforcement behavior.
- Acceptance: Environment docs no longer describe Bluetooth variables as generic host checks only.
- Verification: Run documentation link validation.
- Verification: Run `python tools/update_openapi_snapshot.py --check`.
- Verification: Run `python tools/check_env_registry.py --check-docs`.
- Verification: Run `python tools/check_mirror_drift.py`.
