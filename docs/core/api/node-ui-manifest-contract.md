# Core-Owned Node UI Manifest Contract

Status: Implemented

## Purpose

Core-rendered node UI starts with a node-provided declarative manifest. The manifest tells Core which pages and surfaces exist, where card data lives, and which explicit node actions are available. It does not contain React components, HTML, scripts, or full operational page data.

Nodes expose the manifest at:

```http
GET /api/node/ui-manifest
```

Core owns the manifest schema, validation behavior, rendering, layout, refresh behavior, loading states, error states, and action execution UX.

## Schema

Canonical JSON Schema:

- [node_ui_manifest.schema.json](../../json_schema/node_ui_manifest.schema.json)

Backend validation model:

- `backend/app/nodes/ui_manifest.py`

Current schema version:

- `1.0`

## Manifest Shape

Required top-level fields:

- `schema_version`
- `node_id`
- `node_type`
- `display_name`
- `pages`

Optional top-level fields:

- `manifest_revision`

Each page contains:

- `id`
- `title`
- optional `description`
- one or more `surfaces`

Each surface contains:

- `id`
- `kind`
- `title`
- `data_endpoint`
- optional `description`
- optional `detail_endpoint_template`
- zero or more `actions`
- `refresh`

Card `kind` values are intentionally extensible. Core may render unknown safe kinds as unsupported-card states until a renderer exists.

## Endpoint Rules

Manifest endpoints must be node-local relative paths beginning with `/`.

Allowed examples:

```http
/api/node/ui/overview/health
/api/node/ui/runtime/services
/api/node/ui/voice/intents
/api/voice/intents/{intent_id}
```

Forbidden examples:

```http
http://node.local:8080/api/node/ui/overview/health
javascript:alert(1)
```

## Refresh Policy

Each surface declares one refresh policy.

Supported modes:

- `live`: polling every 1000-5000 ms while visible
- `near_live`: polling every 10000-30000 ms while visible
- `manual`: fetch on open and explicit refresh
- `detail`: fetch only when expanded or selected
- `static`: fetch once until manifest or node revision changes

Polling modes require `interval_ms`. Non-polling modes must not set `interval_ms`.

## Action Rules

Actions are declarative metadata only. A manifest can describe an action, but node endpoints remain authoritative for authorization, validation, and mutation behavior.

Supported action methods:

- `POST`
- `PUT`
- `PATCH`
- `DELETE`

Destructive or sensitive actions must include required confirmation metadata.

## Unsafe Content Rejection

Core rejects manifests that include executable UI or unsafe content.

Rejected content includes:

- node-provided React components
- JSX/component fields
- arbitrary HTML fields
- inline scripts
- browser-executable code fields
- text containing script-like HTML or JavaScript URLs
- absolute or invalid endpoint URLs
- unknown manifest fields
- duplicate page ids
- duplicate surface ids
- duplicate action ids within a surface

## Minimal Example

```json
{
  "schema_version": "1.0",
  "manifest_revision": "rev-1",
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
        }
      ]
    }
  ]
}
```

## Related Docs

- [Frontend and UI](../frontend/frontend-and-ui.md)
- [Proxied UI Contract](../frontend/proxied-ui-contract.md)
- [Node Requirements For Core-Rendered UI](../../nodes/ui-mogration/node-requirements.md)
