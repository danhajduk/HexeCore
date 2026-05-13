# Node Requirements For Core-Rendered UI

Status: Partially implemented

## Purpose

This document defines what each node must eventually provide so Hexe Core can render operational node UI from Core-owned components.

During the first infrastructure phase, implementation tasks are Core-only. Core now has production UI hosting and manifest-advertised rendered-node UI infrastructure, but nodes should not remove their existing operational UI until equivalent operator workflows are verified for that node class.

## Production Assumption

Core-rendered node UI runs from the production Core UI, not the Vite development server.

Node requirements therefore assume:

- the operator browser talks to the Core public origin
- Core talks to node APIs over trusted internal service resolution
- nodes do not require browser access to private node addresses
- node-hosted operational React apps are transitional only
- node-local UI is retained for setup, recovery, and diagnostics while migration is incomplete

## Node-Local UI Policy

After a node is migrated to Core-rendered UI, the node must not serve an independent operational UI.

Node-local UI is allowed only for:

- first-boot setup
- Core pairing and trust registration
- recovery when Core cannot reach or trust the node
- local diagnostics that help repair Core connectivity
- error states that block Core handoff

All normal operator workflows should move to Core-rendered pages. This includes dashboards, health cards, provider status, runtime controls, records, settings, action panels, detail views, artifacts, and event history.

If a node exposes local setup or recovery screens, those screens should clearly hand the operator back to Core once the node is healthy, trusted, and manageable from Core.

## Required Node Surfaces

Each migratable node must eventually expose these surfaces.

### UI Manifest

Endpoint:

```http
GET /api/node/ui-manifest
```

Core reads this endpoint server-side and exposes the validated result to the production Core UI at:

```http
GET /api/nodes/{node_id}/ui-manifest
```

The Core endpoint is admin-session/token protected and returns structured states for untrusted nodes, missing node API endpoints, fetch failures, and contract validation failures.

The manifest must be small and declarative. It describes the global health strip, pages, page snapshot endpoints or legacy surfaces, action endpoints, detail endpoint templates, and refresh policy. It must not include full page data directly in the manifest.

Core frontend code maps manifest `page_endpoint` and legacy `data_endpoint` values through Core-owned node proxy paths. For example, `/api/node/ui/pages/overview` becomes `/api/nodes/{node_id}/node/ui/pages/overview` in the browser.

Core action execution follows the same routing rule for manifest action endpoints. Card data may enable or disable an action id, but the executable method, endpoint, sensitivity, and confirmation metadata must come from the manifest action entry.

Rendered node UI remains gated by a valid Core-rendered UI manifest during migration. Nodes should keep legacy operational UI available until Core can validate that manifest and fallback behavior has been verified.

Canonical Core contract:

- [Core-Owned Node UI Manifest Contract](../../core/api/node-ui-manifest-contract.md)
- [node_ui_manifest.schema.json](../../json_schema/node_ui_manifest.schema.json)

Required manifest fields:

- `schema_version`
- `node_id`
- `node_type`
- `display_name`
- `pages`
- optional top-level `health` surface with kind `health_strip`
- page `id`, `title`, and either `page_endpoint` plus `refresh`, or legacy `surfaces`
- legacy surface `id`, `kind`, `title`, `data_endpoint`, and `refresh`
- action metadata when a surface supports operator actions

Forbidden manifest content:

- React components
- arbitrary HTML
- inline scripts
- browser-executable code
- secrets or credentials
- large full-page data payloads

### Page/Data Endpoints

Nodes should provide one page snapshot endpoint per rendered page. The page snapshot returns the cards and card data for that page in one payload, with a page-level refresh policy.

Expected examples:

```http
GET /api/node/ui/health
GET /api/node/ui/pages/overview
GET /api/node/ui/pages/runtime
```

Legacy per-card data endpoints remain supported during migration:

```http
GET /api/node/ui/overview/warnings
GET /api/node/ui/runtime/services
GET /api/node/ui/{node_domain}/{surface}
```

Page snapshot card data and legacy data responses must be shaped for the Core card kind, not for node frontend internals.

Canonical Core card response contracts:

- [Core-Owned Node UI Card Response Contracts](../../core/api/node-ui-card-response-contracts.md)
- [node_ui_card_responses.schema.json](../../json_schema/node_ui_card_responses.schema.json)

Initial card kinds:

- `node_overview`
- `health_strip`
- `facts_card`
- `warning_banner`
- `action_panel`
- `runtime_service`
- `provider_status`

Later card kinds:

- `record_list`
- `detail_drawer`
- `settings_form`
- `resource_grid`
- `artifact_browser`
- `event_timeline`

### Detail Endpoints

Nodes must expose detail endpoints only for records the operator opens or selects. Detail data should not be bundled into the manifest or initial page payload.

Examples:

```http
GET /api/voice/intents/{intent_id}
GET /api/gmail/messages/{message_id}
GET /api/scheduled-tasks/{task_id}
```

### Action Endpoints

Nodes must expose explicit action endpoints for mutations and operator commands.

Examples:

```http
POST /api/voice/intents/dispatch
POST /api/voice/intents/invoke
PUT /api/tts/settings
POST /api/services/restart
POST /api/gmail/fetch
POST /api/scheduled-tasks/{task_id}/retry
```

Actions must remain authoritative on the node side. A manifest can describe an action, but it must not grant permission by itself.

## Refresh Requirements

Each surface must declare one refresh mode.

Supported modes:

- `live`: poll every 1-5 seconds while visible
- `near_live`: poll every 10-30 seconds while visible
- `manual`: fetch on page/card open and explicit refresh
- `detail`: fetch only when expanded or selected
- `static`: fetch once until the manifest or node revision changes

Nodes should avoid endpoints that require Core to fetch every operational detail up front.

## Security Requirements

Nodes must preserve existing trust boundaries.

Required behavior:

- authorize every manifest, data, detail, and action endpoint
- validate all action input server-side
- avoid returning secrets in UI data responses
- reveal sensitive detail data only when the operator has permission
- return structured status and error payloads
- include confirmation metadata in the manifest for destructive or sensitive actions

Core must treat node manifest content as untrusted data. Nodes must treat Core calls as privileged only when they carry valid trusted credentials or service tokens.

## Node UI Modes

Nodes should eventually support these local UI modes:

- `full`: current node-hosted operational UI, useful during migration
- `setup_only`: first boot, Core pairing, trust registration, recovery diagnostics, and handoff to Core
- `disabled`: no node-hosted UI except health/API surfaces

Initial migration should keep nodes in `full`. Mature nodes should move to `setup_only` after Core-rendered UI has operational parity. `disabled` should wait until Core has strong recovery and diagnostics coverage.

`setup_only` is the intended steady state for most migrated nodes. A mature node should not stay in `full` unless it has documented setup, recovery, or error-handling needs that Core cannot cover yet.

## Minimum Pilot Node Contract

A first pilot node should provide:

- `/api/node/ui-manifest`
- `/api/node/ui/health`
- `/api/node/ui/overview/warnings`
- `/api/node/ui/runtime/services`
- one domain-specific summary endpoint
- one detail endpoint if the domain surface lists records
- one safe action endpoint for proving Core action execution

The existing node-hosted UI must remain unchanged during the pilot.

## What Nodes Should Not Do

Nodes should not:

- ship Core operational card React components
- require the browser to fetch from private node addresses
- embed local dev server URLs in manifests or card data
- expose one giant endpoint containing all node operational state
- rely on the manifest as an authorization mechanism
- remove setup/recovery UI before Core provides equivalent operational coverage
- keep a parallel independent operational UI after Core-rendered UI reaches parity
