# Core-Rendered Node UI Migration

Status: Partially implemented

## Purpose

Move Hexe node operator UIs toward a shared Core-rendered model. Nodes should expose structured UI manifests, data endpoints, and action endpoints. Core should own layout, visual design, navigation, permissions UX, card components, and refresh behavior.

The goal is one consistent Core experience across Voice, Email, AI, Interaction, and future nodes while allowing each node to remain domain-specific through its data, capabilities, and actions.

## Current Core Infrastructure

Status: Implemented

Core now includes the infrastructure needed to pilot this migration:

- production Core UI hosting from the built `frontend/dist` artifact
- admin-gated manifest fetch endpoint at `GET /api/nodes/{node_id}/ui-manifest`
- Core manifest and card response validators with JSON Schemas
- frontend data loaders for manifest and surface endpoints
- shared renderer registry for the initial card kinds
- manifest-backed page shell at `/nodes/:nodeId/rendered-ui`
- Core-routed action execution from manifest metadata
- rendered-node UI feature gate with legacy `/nodes/:nodeId/UI` fallback
- pilot fixtures and integration tests for the initial card set

Node-side implementation remains Not developed in this repository. Nodes still need to expose their own `/api/node/ui-manifest`, card data endpoints, detail endpoints, and action endpoints.

## Target Model

Nodes should not serve rich operational cards as standalone React apps. Instead:

- Nodes own capabilities, state, domain data, schemas, and actions.
- Core owns the user interface, card grammar, theme, responsive behavior, and operator workflow.
- Node-local UI becomes setup, recovery, and diagnostics only.

Recommended long-term local UI modes:

- `full`: current node-hosted operational UI, useful during migration.
- `setup_only`: first boot, Core pairing, trust registration, recovery diagnostics, and handoff to Core.
- `disabled`: no node-hosted UI except health/API surfaces.

## High-Level Flow

1. Core discovers a trusted node through existing registration and service discovery.
2. Core fetches a lightweight node UI manifest.
3. Core renders node pages and card placeholders from the manifest.
4. Core lazily fetches only the data for visible pages/cards.
5. Core calls node action endpoints when operators press buttons or submit forms.
6. Node enforces trust, permissions, validation, and domain behavior.

```text
Core
  -> GET node /api/node/ui-manifest
  -> render Core-owned page/card shells
  -> GET card-specific data endpoints only when visible
  -> POST/PUT/PATCH/DELETE action endpoints on operator command

Node
  -> publishes UI manifest
  -> exposes stable data endpoints
  -> exposes explicit action endpoints
  -> returns structured status/errors
```

## UI Manifest

Each node should expose a small manifest that describes pages, surfaces, data endpoints, action endpoints, and refresh policy. The manifest should not contain full page data.

Node endpoint:

```http
GET /api/node/ui-manifest
```

Example:

```json
{
  "schema_version": "1.0",
  "node_id": "voice-node-1",
  "node_type": "voice",
  "display_name": "Voice Node",
  "pages": [
    {
      "id": "overview",
      "title": "Overview",
      "surfaces": [
        {
          "id": "node.health",
          "kind": "health_strip",
          "title": "Node Health",
          "data_endpoint": "/api/node/ui/overview/health",
          "refresh": {
            "mode": "near_live",
            "interval_ms": 15000
          }
        },
        {
          "id": "node.warnings",
          "kind": "warning_banner",
          "title": "Operational Warnings",
          "data_endpoint": "/api/node/ui/overview/warnings",
          "refresh": {
            "mode": "manual"
          }
        }
      ]
    },
    {
      "id": "voice.intents",
      "title": "Intents",
      "surfaces": [
        {
          "id": "voice.intent_registry",
          "kind": "record_list",
          "title": "Registered Intents",
          "data_endpoint": "/api/node/ui/voice/intents",
          "detail_endpoint_template": "/api/voice/intents/{intent_id}",
          "actions": [
            {
              "id": "test_intent",
              "label": "Test Intent",
              "method": "POST",
              "endpoint": "/api/voice/intents/dispatch"
            },
            {
              "id": "invoke_intent",
              "label": "Invoke Intent",
              "method": "POST",
              "endpoint": "/api/voice/intents/invoke"
            }
          ],
          "refresh": {
            "mode": "manual",
            "cache_ttl_ms": 10000
          }
        }
      ]
    }
  ]
}
```

## Data Loading

Core should not request all node data up front. Each visible page/card should load its own data through a Core-managed data layer.

Preferred behavior:

- Fetch the manifest on node page entry.
- Fetch page-level summary cards when the page becomes visible.
- Fetch detail records only when an operator opens a drawer, popout, or row detail.
- Poll only cards that are visible and marked as live or near-live.
- Cancel or pause polling when the operator leaves the page.
- Cache short-lived responses by node id, surface id, and endpoint.

Core cards should not blindly call `fetch()` independently. A shared Core data layer should coordinate caching, deduplication, loading states, errors, and refresh actions.

Recommended refresh modes:

- `live`: poll every 1-5 seconds while visible.
- `near_live`: poll every 10-30 seconds while visible.
- `manual`: fetch on page/card open and refresh button.
- `detail`: fetch only when expanded or selected.
- `static`: fetch once until the manifest or node revision changes.

## Shared Core Card Vocabulary

Core should render a constrained set of reusable card kinds. Nodes select card kinds and provide data endpoints; nodes do not ship React components or HTML for normal operational UI.

Initial shared card kinds:

- `node_overview`: identity, lifecycle, trust, software, and Core pairing.
- `health_strip`: compact status chips for lifecycle, trust, Core, governance, providers, and node-specific health.
- `facts_card`: labeled key/value facts.
- `warning_banner`: warning list plus recovery actions.
- `action_panel`: grouped operator actions.
- `record_list`: table or card list with optional detail drawer and row actions.
- `settings_form`: schema-backed settings form.
- `runtime_service`: service/process health and restart actions.
- `provider_status`: provider health, account/model summary, quotas, and errors.
- `resource_grid`: model, prompt, media, file, or artifact cards.
- `event_timeline`: recent events, sessions, or task history.
- `artifact_browser`: files, recordings, logs, media, and generated assets.
- `detail_drawer`: shared detail surface for selected records.

## Shared vs Node-Unique Surfaces

Many current Voice and Email cards can share the same Core renderer with different manifest/data.

Good shared candidates:

- Node overview.
- Health strip.
- Core connection and governance status.
- Operational warnings.
- Sidebar navigation.
- Operator actions.
- Live status facts.
- Provider status.
- Runtime/service controls.
- Registry/list cards.
- Settings forms.
- Detail popouts/drawers.

Node-unique data that should still use shared primitives:

- Voice endpoint state, mute, volume, replay, media transfer, firmware update.
- Voice speech pipeline, transcript, response, STT/TTS latency.
- Voice intent registry, tester, and invoker.
- Voice TTS model warming and sample-rate settings.
- Gmail mailbox status, quotas, fetch actions, and classification pipeline.
- Gmail sender reputation.
- Gmail scheduled tasks.
- Gmail tracked orders and shipments.
- AI model/runtime state.
- Interaction-node domain events and intent ownership.

The design should merge the card grammar, not erase node personality. A Voice page should still feel voice-specific because the data, actions, and labels are voice-specific.

## Recognized Card Candidates

The first migration inventory compared the current Voice Node and Email Node frontends. These are the concrete candidates already recognized for Core-rendered reuse.

### Direct Shared Renderer Candidates

These cards should become shared Core renderers with node-provided labels, facts, chips, and actions.

| Candidate | Current Voice surface | Current Email surface | Proposed Core card kind |
| --- | --- | --- | --- |
| Node overview | `NodeOverviewCard` | `NodeOverviewCard` | `node_overview` |
| Node health strip | `NodeHealthStripCard` | `NodeHealthStripCard` | `health_strip` |
| Core connection | `CoreConnectionCard` | `CoreConnectionCard` | `facts_card` or `provider_status` |
| Operational warnings | `OperationalWarningsCard` | `OperationalWarningsCard` | `warning_banner` |
| Dashboard sidebar | `DashboardSidebarCard` | `DashboardSidebarCard` | Core navigation model |
| Dashboard actions | `DashboardActionsCard` | `DashboardActionsCard` | `action_panel` |
| Setup stage wrapper | `StageCard` | `StageCard` | `setup_stage` |
| Live status | `LiveStatusCard` | `LiveStatusCard` | `facts_card` |
| Node identity setup | `NodeIdentityFormCard` | `NodeIdentityFormCard` | `settings_form` |
| Setup hero | `SetupHeroCard` | `SetupHeroCard` | `setup_summary` |
| Operator prompts | `OperatorPromptsCard` | `OperatorPromptsCard` | `action_panel` or `warning_banner` |

### Same Card Code, Node-Unique Data

These should feel domain-specific, but they can be rendered by the same Core card components.

| Shared card kind | Voice examples | Email examples |
| --- | --- | --- |
| `provider_status` | STT provider, TTS provider, Piper model state, endpoint provider readiness | Gmail provider state, account status, quota, mailbox health |
| `action_panel` | refresh endpoint, test assistant turn, stop session, replay response, mute, volume | Gmail fetch, Spamhaus check, sender reputation refresh, classifier batch |
| `record_list` | registered intents, voice sessions, endpoint media assets | scheduled tasks, tracked orders, shipments, review/action-required records |
| `resource_grid` | TTS models, generated TTS artifacts, wake recordings, endpoint media | sender reputation records, training records, tracked order records |
| `settings_form` | TTS warm voices, conversion sample rates, provider selection | Gmail windows, scheduler settings, sender label rules, retention settings |
| `runtime_service` | backend, STT engine, TTS engine, wake runtime, Piper runtime | backend, provider workers, scheduler/runtime task execution |
| `detail_drawer` | intent contract detail, TTS model detail, session detail, endpoint detail | tracked order detail, scheduled task error detail, email/message detail |
| `event_timeline` | voice turn events, session history, command acknowledgements | mail processing pipeline, scheduled task history, classification execution |

### Voice-Unique Surfaces

These should remain Voice-domain surfaces, but use shared cards internally.

- Voice endpoint state projection: connection, transport, UX state, session state.
- Endpoint controls: mute, volume, stop session, replay response, reconnect.
- Speech pipeline: transcript, assistant response, STT latency, assistant latency, TTS latency, total latency.
- Voice sessions: history, replay, detail inspection, artifacts.
- Registered intents: intent cards/list, contract detail, test dispatch, invoke intent.
- TTS runtime: Piper/Kokoro model inventory, warm/cold model state, sample-rate conversion settings.
- Endpoint media and storage: media assets, delivery, inventory, reformat controls.
- Firmware update status and OTA push.
- Wake recordings and voice artifacts.

### Email-Unique Surfaces

These should remain Email-domain surfaces, but use shared cards internally.

- Gmail mailbox state: account, unread counts, stored emails, classified counts, quota.
- Gmail fetch actions: initial learning, today, yesterday, last hour.
- Classification pipeline: local classifier, AI fallback, batch progress, execution results.
- Spamhaus checks and sender reputation.
- Sender reputation training and manual classification.
- Scheduled task table with retry and last-error detail.
- Tracked orders and shipments: table, detail drawer, edit form, AI decision regeneration.
- Gmail settings: scheduler windows, sender label rules, full HTML extraction, retention controls.
- Review/action-required inboxes and family coverage views.

### Early Core Renderer Priority

Build the Core renderer set in this order:

1. `node_overview`, `health_strip`, `facts_card`, and `warning_banner`.
2. `action_panel`, `runtime_service`, and `provider_status`.
3. `record_list` with `detail_drawer`.
4. `settings_form` for node-owned settings.
5. `resource_grid`, `artifact_browser`, and `event_timeline`.

This order moves the shared node shell first, then operational controls, then heavier domain pages.

## API Shape

Use three endpoint categories.

### Manifest Endpoints

Describe what Core can render.

```http
GET /api/node/ui-manifest
```

### Summary/Data Endpoints

Return the data for a visible card or page section.

Examples:

```http
GET /api/node/ui/overview/health
GET /api/node/ui/overview/warnings
GET /api/node/ui/runtime/services
GET /api/node/ui/voice/intents
GET /api/node/ui/voice/endpoint
GET /api/node/ui/voice/tts
GET /api/node/ui/gmail/status
GET /api/node/ui/gmail/scheduled-tasks
GET /api/node/ui/gmail/tracked-orders
```

### Detail and Action Endpoints

Return detail records or mutate node state.

Examples:

```http
GET /api/voice/intents/{intent_id}
POST /api/voice/intents/dispatch
POST /api/voice/intents/invoke
PUT /api/tts/settings
POST /api/services/restart
GET /api/gmail/messages/{message_id}
POST /api/gmail/fetch
POST /api/scheduled-tasks/{task_id}/retry
```

## Response Conventions

Card data responses should be shaped for the card kind, not for arbitrary frontend internals.

Example `health_strip` response:

```json
{
  "updated_at": "2026-05-13T01:00:00Z",
  "items": [
    {
      "id": "lifecycle",
      "label": "Lifecycle",
      "value": "operational",
      "tone": "success"
    },
    {
      "id": "trust",
      "label": "Trust",
      "value": "trusted",
      "tone": "success"
    },
    {
      "id": "stt",
      "label": "STT",
      "value": "faster_whisper",
      "tone": "success"
    }
  ]
}
```

Example `record_list` response:

```json
{
  "updated_at": "2026-05-13T01:00:00Z",
  "summary": {
    "registered_count": 22,
    "active_count": 22
  },
  "columns": [
    { "id": "name", "label": "Name" },
    { "id": "status", "label": "Status" },
    { "id": "owner", "label": "Owner" },
    { "id": "updated_at", "label": "Updated" }
  ],
  "records": [
    {
      "id": "timer.create",
      "name": "Create timer",
      "status": "active",
      "owner": "hexe-interaction",
      "updated_at": "2026-05-13T01:00:00Z",
      "detail_ref": {
        "endpoint": "/api/voice/intents/timer.create"
      }
    }
  ]
}
```

## Security and Trust

Core-rendered node UI must preserve node security boundaries.

Requirements:

- Core must call node endpoints with trusted node credentials or service tokens.
- Nodes must authorize every data and action endpoint.
- Manifests must not grant actions by themselves; node endpoints remain authoritative.
- Destructive or sensitive actions should include metadata for Core confirmation UX.
- Nodes should avoid exposing secrets in UI data responses.
- Detail endpoints should reveal sensitive data only when the operator has permission.
- Core should treat node manifest content as untrusted data, not executable UI.

Avoid:

- Node-supplied React components for normal cards.
- Node-supplied arbitrary HTML.
- Inline scripts from node manifests.
- One giant endpoint that dumps every node detail into Core on first load.

## Migration Plan

### Phase 1: Document and Inventory

- Inventory common cards across Voice, Email, AI, Interaction, and Core.
- Define the first manifest schema.
- Define shared response shapes for `health_strip`, `facts_card`, `record_list`, `action_panel`, and `settings_form`.

### Phase 2: Add Node Manifests

- Add `/api/node/ui-manifest` to one node first.
- Start with overview, health, warnings, runtime, and one domain page.
- Keep existing node UI unchanged during this phase.

### Phase 3: Build Core Renderers

- Add Core renderers for initial card kinds.
- Add a Core data layer for lazy loading, caching, refresh policy, and polling while visible.
- Add generic loading, error, stale-data, and retry states.

### Phase 4: Move Operational Pages

- Migrate operational node pages into Core one at a time.
- Keep node-local setup and recovery screens.
- Use existing node endpoints where they already fit.
- Add summary/detail endpoints where existing endpoints are too heavy.

### Phase 5: Reduce Node UIs

- Add node UI mode configuration.
- Default mature nodes to `setup_only`.
- Keep `full` available during transition.
- Consider `disabled` only after Core has strong recovery and diagnostics coverage.

## Open Questions

- Where should manifest schemas live: Core repo, shared docs, or per-node docs with a canonical Core copy?
- Should Core store per-node UI preferences such as hidden cards, ordering, and refresh intervals?
- How should Core handle incompatible manifest versions?
- Should nodes publish UI manifest changes through capability declaration, or should Core always fetch live manifests?
- What is the first minimum card set that makes a node useful inside Core?
- Do some high-trust admin actions require a separate confirmation token or signed challenge?

## Initial Recommendation

Start with a conservative declarative system:

- Core owns all rendering.
- Nodes publish manifests and data/action endpoints.
- Cards load data independently through a Core-managed data layer.
- Polling is opt-in and visibility-aware.
- Node-local UI shrinks to setup/recovery after Core reaches feature parity.

This gives Hexe a unified operator experience without turning every node into a separate frontend application.
