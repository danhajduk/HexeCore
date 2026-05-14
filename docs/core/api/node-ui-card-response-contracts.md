# Core-Owned Node UI Card Response Contracts

Status: Implemented

## Purpose

Core-rendered node UI cards load card-specific data from node endpoints. Nodes provide data shaped for Core-owned card kinds; nodes do not provide React components, HTML, or presentation code.

Canonical schema catalog:

- [node_ui_card_responses.schema.json](../../json_schema/node_ui_card_responses.schema.json)

Backend validation models:

- `backend/app/nodes/ui_cards.py`

Core frontend renderer registry:

- `frontend/src/core/rendered-node-ui/renderers.tsx`

Pilot contract fixtures:

- `backend/tests/fixtures/node_ui_pilot.py`
- `frontend/src/core/rendered-node-ui/pilotFixtures.ts`

## Shared Response Fields

Every initial card response includes:

- `kind`: card kind for the response
- `updated_at`: timestamp for the data snapshot
- `stale`: whether the card data is known stale
- `empty`: whether the endpoint has no domain data to show
- `errors`: structured card-level errors
- `retry`: optional retry metadata

Card responses reject unknown fields and unsafe executable text. Core card payloads must not expose secret-like fields such as passwords, tokens, API keys, credentials, private keys, or session cookies.

## Initial Card Kinds

Implemented initial response contracts:

- `node_overview`
- `health_strip`
- `facts_card`
- `warning_banner`
- `action_panel`
- `record_list`
- `runtime_service`
- `provider_status`

Later card kinds such as `detail_drawer`, `settings_form`, `resource_grid`, `artifact_browser`, and `event_timeline` remain `Not developed`.

## Tone Vocabulary

Common tone values:

- `neutral`
- `info`
- `success`
- `warning`
- `error`
- `danger`

## Action State

Action-bearing cards refer to action ids from the manifest. A card data response may mark an action enabled or disabled and may include a short `reason` or `disabled_reason`. Card data does not grant permission to execute an action; node action endpoints remain authoritative.

## Examples

### `health_strip`

Each health strip item carries the display name of the state, the current state, and the tone flag Core uses for color coding.

```json
{
  "kind": "health_strip",
  "updated_at": "2026-05-13T01:00:00Z",
  "items": [
    {
      "state_name": "Lifecycle",
      "current_state": "operational",
      "tone": "success"
    },
    {
      "state_name": "Trust",
      "current_state": "trusted",
      "tone": "success"
    }
  ]
}
```

### `action_panel`

```json
{
  "kind": "action_panel",
  "updated_at": "2026-05-13T01:00:00Z",
  "groups": [
    {
      "id": "runtime",
      "label": "Runtime",
      "actions": [
        {
          "id": "restart_service",
          "label": "Restart service",
          "enabled": true,
          "tone": "warning"
        }
      ]
    }
  ]
}
```

### `record_list`

`record_list` is the reusable shape for endpoint lists, sessions, intents, artifacts, inventories, and other tabular node resources. `records` may include domain-specific scalar fields in addition to the shared `id`, `name`, `status`, `tone`, `active`, and `detail_ref` fields.

```json
{
  "kind": "record_list",
  "updated_at": "2026-05-13T01:00:00Z",
  "summary": {
    "record_count": 1
  },
  "columns": [
    { "id": "name", "label": "Name" },
    { "id": "status", "label": "Status" }
  ],
  "records": [
    {
      "id": "endpoint-1",
      "name": "Endpoint 1",
      "status": "online",
      "tone": "success",
      "detail_ref": { "endpoint": "/api/endpoint/status/endpoint-1" }
    }
  ]
}
```

### `runtime_service`

`runtime_service` is the reusable shape for runtime components such as backend processes, worker services, provider daemons, schedulers, wake-word services, and model runtimes. Nodes may provide canonical `runtime_state`/`health_status` fields, display-oriented `state`/`tone`, provider/model summaries, resource usage, restart metadata, facts, and action states. Service-level action states should reference manifest/page-card actions, commonly node-owned `POST` endpoints such as `/api/node/ui/runtime/services/{service_id}/{start|stop|restart}`.

```json
{
  "kind": "runtime_service",
  "updated_at": "2026-05-13T01:00:00Z",
  "services": [
    {
      "id": "backend",
      "label": "Backend",
      "state": "running",
      "tone": "success",
      "healthy": true,
      "provider": "systemd",
      "resource_usage": {
        "process_cpu_percent": 1.5,
        "process_memory_rss_bytes": 104857600
      },
      "restart_supported": true,
      "restart_target": "backend",
      "actions": [
        { "id": "runtime_service.backend.restart", "label": "Restart" }
      ]
    }
  ],
  "actions": [
    { "id": "refresh_runtime", "label": "Refresh Runtime" }
  ]
}
```

### `provider_status`

```json
{
  "kind": "provider_status",
  "updated_at": "2026-05-13T01:00:00Z",
  "providers": [
    {
      "id": "stt",
      "label": "STT Provider",
      "provider": "faster_whisper",
      "state": "ready",
      "tone": "success",
      "facts": [
        {
          "id": "model",
          "label": "Model",
          "value": "small.en"
        }
      ],
      "setup": {
        "facts": [
          {
            "id": "enabled",
            "label": "Enabled",
            "value": true
          }
        ],
        "errors": [],
        "actions": []
      }
    }
  ]
}
```

Provider cards should keep the card body compact. Use `facts` and `quotas` for status details shown in the detail popup, and optional `setup.facts`, `setup.errors`, and `setup.actions` for provider configuration state or setup controls.

## Related Docs

- [Core-Owned Node UI Manifest Contract](./node-ui-manifest-contract.md)
- [Frontend and UI](../frontend/frontend-and-ui.md)
- [Node Requirements For Core-Rendered UI](../../nodes/ui-mogration/node-requirements.md)
