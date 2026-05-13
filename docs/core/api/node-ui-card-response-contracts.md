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
- `runtime_service`
- `provider_status`

Later card kinds such as `record_list`, `detail_drawer`, `settings_form`, `resource_grid`, `artifact_browser`, and `event_timeline` remain `Not developed`.

## Tone Vocabulary

Common tone values:

- `neutral`
- `info`
- `success`
- `warning`
- `error`
- `danger`

## Action State

Action-bearing cards refer to action ids from the manifest. A card data response may mark an action enabled or disabled and may include a short reason. Card data does not grant permission to execute an action; node action endpoints remain authoritative.

## Examples

### `health_strip`

```json
{
  "kind": "health_strip",
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
      ]
    }
  ]
}
```

## Related Docs

- [Core-Owned Node UI Manifest Contract](./node-ui-manifest-contract.md)
- [Frontend and UI](../frontend/frontend-and-ui.md)
- [Node Requirements For Core-Rendered UI](../../nodes/ui-mogration/node-requirements.md)
