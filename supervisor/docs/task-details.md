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
- Preserve node-side requirements under `docs/nodes/ui-mogration/`.
- Existing node-hosted operational UIs must remain usable until Core-rendered UI reaches feature parity.
- Use existing Core conventions for backend, frontend, scripts, systemd units, tests, and docs.
- Make minimal, production-ready changes in small reviewable units.
- Commit completed implementation work task-by-task when this queue is executed.

Reference docs and code to inspect before implementation:

- `docs/nodes/future-dev/core-rendered-node-ui-migration.md`
- `docs/nodes/ui-mogration/README.md`
- `docs/nodes/ui-mogration/node-requirements.md`
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
- Task 947 updates verified docs after implementation only. It must update Core frontend/API docs and node migration handoff docs to reflect implemented behavior, link canonical Core contracts from `docs/nodes/ui-mogration/node-requirements.md`, and avoid documenting planned behavior as implemented.

Definition of done preserved from the original planning block:

- Core production UI no longer depends on the Vite dev server.
- Core serves the built UI without breaking API, node proxy, addon proxy, or websocket routes.
- Backend reload/rebuild helper scripts do not leave production Core serving stale or missing UI assets.
- Core owns rendered node UI layout, cards, data loading, refresh behavior, actions, and operator states.
- Nodes provide manifests, data endpoints, detail endpoints, and action endpoints only.
- Node-local UI remains available for setup, recovery, diagnostics, and migration fallback.
- The first pilot can render useful node operational UI in Core without requiring node repository changes in this queue.

## Task 948-956
Original task details preserved from the AI node resource-history investigation.

Active normalized queue entries:

- Task 948: Add Supervisor resource history store and retention policy
- Task 949: Persist Supervisor host resource samples
- Task 950: Persist Supervisor runtime resource samples
- Task 951: Record Supervisor runtime lifecycle markers in resource timelines
- Task 952: Expose Supervisor resource history APIs
- Task 953: Add tests for Supervisor resource history collection and APIs
- Task 954: Update docs and schemas for Supervisor-owned resource history
- Task 955: Add Core UI resource history views for Supervisor timelines
- Task 956: Support remote Supervisor resource history access from Core

Preserved rationale:

- The Supervisor should own resource history because CPU, RAM, swap, disk, GPU, VRAM, system load, process health, exits, restarts, and crash markers are host-level facts.
- The Supervisor survives and observes Nodes, while Nodes are the processes that may crash or be killed. If an AI node segfaults or exits under memory pressure, node-owned history is the data most likely to be incomplete.
- Nodes should continue to own request and execution metrics such as in-flight counts, queue and admission decisions, model/provider latency, token counts, request errors, benchmark results, and per-request metadata.
- Supervisor-owned and node-owned telemetry should be correlated by timestamp rather than forcing the Supervisor to understand request-level node semantics.

Implementation scope:

- Task 948 should define a lightweight persisted time-series store for Supervisor-owned resource history, with a default retention window of 3 days, range parsing, step/downsampling behavior, and durable storage location. Reuse any existing stats-store pattern in the broader app when it fits.
- Task 949 should persist host-level samples already available to the Supervisor resource monitor: CPU, load average, RAM, swap when available, root disk, network counters/rates, GPU utilization, VRAM, GPU temperature, and GPU power.
- Task 950 should persist per-runtime samples for registered runtimes, services, processes, and containers using Supervisor-observed resource data such as pid/container identity, CPU, memory, RSS, process status, and resource source.
- Task 951 should append timeline markers for lifecycle events such as start, stop, restart, exit, missing process, OOM indicators where observable, segfault or signal markers where observable, and last error transitions.
- Task 952 should expose APIs on the Supervisor service, including standalone and remote Supervisor deployments, equivalent to:
  - `GET /api/supervisor/resources/history?range=24h&step=60s`
  - `GET /api/supervisor/runtimes/{node_id}/resources/history?range=24h`
  Responses should make timestamp correlation straightforward and avoid leaking node request metadata.
- Task 953 should cover store retention, downsampling/range behavior, host sample persistence, runtime sample persistence, lifecycle marker persistence, and router contracts.
- Task 954 should document the Supervisor/Node telemetry ownership boundary, the 3-day retention default, local versus remote Supervisor behavior, and update any relevant JSON schemas or API docs.
- Task 955 should add an operator-facing Core UI view for recent Supervisor host and runtime timelines, focused on crash debugging such as correlating high VRAM/RAM/swap pressure with a backend exit.
- Task 956 should route Core history reads through the configured Supervisor client path so local and remote Supervisors expose the same history behavior, auth/error handling, range parameters, and runtime id filtering.

Definition of done:

- Supervisor keeps recent host and runtime resource history even when a Node process crashes.
- Supervisor retains resource history for 3 days by default.
- Operators can retrieve resource history by time range and, where applicable, by runtime id.
- Core can retrieve equivalent resource history from local and remote Supervisor services.
- Runtime crash/debug timelines can show resource pressure immediately before exits or restarts.
- Node-owned request metrics remain separate and are not required for Supervisor resource history.

## Task 957-963
Original task details preserved from the request to remove remaining Synthia naming and replace it with Hexe, including environment files.

Active normalized queue entries:

- Task 957: Audit all remaining Synthia identifiers and compatibility requirements
- Task 958: Rename Synthia code packages, modules, and imports to Hexe
- Task 959: Rename Synthia environment variables and env file entries to Hexe
- Task 960: Rename Synthia service, script, systemd, and runtime artifact names to Hexe
- Task 961: Rename Synthia documentation, schemas, UI text, and fixtures to Hexe
- Task 962: Add backward-compatible migration handling for legacy Synthia config
- Task 963: Add tests and repo checks proving Synthia references are removed or explicitly legacy

Preserved rationale:

- Hexe should be the canonical product, service, package, API, environment, documentation, and operator-facing name.
- Any remaining Synthia references should either be removed, renamed to Hexe, or explicitly isolated as legacy migration compatibility with a planned removal path.
- Environment files are in scope. Do not skip `.env`, `.env.example`, `.config`, deployment templates, systemd environment files, onboarding examples, or generated config defaults.

Implementation scope:

- Task 957 should produce an inventory of all remaining `synthia`, `Synthia`, and `SYNTHIA` references across tracked files, ignored config templates where safe, scripts, docs, schemas, frontend text, backend modules, service names, systemd units, and env examples. Classify each as rename-now, migrate-with-compatibility, or intentional legacy.
- Task 958 should rename code-level packages, modules, imports, class names, route labels, loggers, tests, and fixtures from Synthia to Hexe where the rename can be made without breaking persisted user data.
- Task 959 should rename environment variables and env file keys from `SYNTHIA_*` to `HEXE_*`, including `core/.config/hexe/*.env` style local config files, `.env.example` files, deployment templates, and documented examples. Avoid changing secret values; rename keys and references only.
- Task 960 should rename service names, script identifiers, systemd unit names, process names, runtime artifact names, directories, and generated files where they still carry Synthia branding.
- Task 961 should update docs, JSON schemas, UI labels, screenshots references, fixtures, comments, and operator-facing text so Hexe is canonical everywhere.
- Task 962 should add migration or fallback handling for existing installations that still have `SYNTHIA_*` environment variables, legacy config keys, persisted paths, or service names. Prefer warning and compatibility shims where immediate hard breaks would strand existing deployments.
- Task 963 should add targeted tests and repo checks that fail on new unapproved Synthia references, while allowing explicitly documented legacy compatibility references until their removal window closes.

Definition of done:

- New installs use Hexe names exclusively across code, services, docs, schemas, scripts, and env files.
- Existing installs with legacy Synthia env/config can migrate or continue long enough to receive clear operator guidance.
- Secret values in env files are not regenerated or altered as part of the rename unless explicitly required.
- Any remaining Synthia references are limited to documented legacy compatibility code/tests.
