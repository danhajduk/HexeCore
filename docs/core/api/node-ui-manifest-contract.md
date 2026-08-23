# Core-Owned Node UI Manifest Contract

Status: Implemented

## Purpose

Core-rendered node UI starts with a node-provided declarative manifest. The manifest tells Core which global health strip and pages exist and how each page should be loaded. A page can either point to a page snapshot endpoint that returns all card data for the page, or use the older per-surface data endpoint model during migration. It does not contain React components, HTML, scripts, or browser-executable code.

Nodes expose the manifest at:

```http
GET /api/node/ui-manifest
```

Core owns the manifest schema, validation behavior, rendering, layout, refresh behavior, loading states, error states, and action execution UX.

## Core Fetch API

Core exposes the validated manifest to the production Core UI through:

```http
GET /api/nodes/{node_id}/ui-manifest
```

This route is admin-session/token protected. The browser calls Core only; Core resolves the node API base URL and fetches the node-local manifest endpoint server-side. Core prefers registration API metadata and can fall back to the supervisor runtime API base when registration metadata is missing.

Response shape:

- `ok`: `true` when Core fetched and validated the manifest
- `status`: one of `available`, `node_not_found`, `node_not_trusted`, `endpoint_not_configured`, `fetch_failed`, or `invalid_manifest`
- `manifest`: the validated manifest payload when `ok=true`
- `manifest_revision`: the active manifest revision when provided by the node
- `cached_manifest_revision`: the most recent valid revision Core has seen for the node, when available
- `error_code` and `detail`: operator-readable failure state when `ok=false`

Core fetches manifests only for trusted nodes. Core caches valid manifests by node id and manifest revision when a revision is provided. Unversioned manifests are cached as the latest unversioned manifest for that node. Once a valid manifest is cached, Core serves that cached manifest immediately and refreshes the node manifest in the background after the refresh window, so rendered UI page loads do not block on intermittent manifest fetch latency.

## Schema

Canonical JSON Schema:

- [node_ui_manifest.schema.json](../../json_schema/node_ui_manifest.schema.json)

Backend validation model:

- `backend/app/nodes/ui_manifest.py`

Core fetch/validation service:

- `backend/app/nodes/ui_manifest_service.py`

Core frontend data-loading layer:

- `frontend/src/core/rendered-node-ui/`

Core manifest-backed page shell:

- `frontend/src/core/pages/RenderedNodeUiPage.tsx`

Core action execution layer:

- `frontend/src/core/rendered-node-ui/api.ts`
- `frontend/src/core/pages/RenderedNodeUiPage.tsx`

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
- `health`: a top-level `health_strip` surface rendered above the tabs on every page

Each page contains:

- `id`
- `title`
- optional `description`
- either `page_endpoint` plus `refresh`, or one or more legacy `surfaces`

The top-level `health` surface uses the same surface shape as page surfaces, but its `kind` must be `health_strip`. Core renders it once above the tab bar and fetches its `data_endpoint` independently from page snapshot or page surface calls.

Preferred page snapshot fields:

- `page_endpoint`: node-local API path returning the page cards and card data
- `refresh`: page-level refresh policy

Legacy surface fields remain supported during migration:

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

## Page Snapshot Shape

When a page declares `page_endpoint`, Core fetches that endpoint through the Core node proxy and renders the returned `cards` directly. This lets a node return one consistent page snapshot instead of requiring one fetch per card.

Required page snapshot fields:

- `page_id`
- `cards`

Optional page snapshot fields:

- `updated_at`
- `refresh`

Each card contains:

- `id`
- `kind`
- `data`
- optional `title`
- optional `description`
- optional `detail_endpoint_template`
- zero or more `actions`
- optional `refresh`

Card `data` uses the existing Core card response contracts. Core filters redundant `node_overview` cards from live page rendering because the header and health strip already carry that information.

## Endpoint Rules

Manifest endpoints must be node-local relative paths beginning with `/`.

Allowed examples:

```http
/api/node/ui/health
/api/node/ui/pages/overview
/api/node/ui/runtime/services
/api/node/ui/voice/intents
/api/voice/intents/{intent_id}
```

Forbidden examples:

```http
http://node.local:8080/api/node/ui/health
javascript:alert(1)
```

## Refresh Policy

Each page snapshot page declares one page-level refresh policy. Legacy surfaces each declare their own refresh policy.

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

Preferred page snapshot manifest:

```json
{
  "schema_version": "1.0",
  "manifest_revision": "rev-1",
  "node_id": "voice-node-1",
  "node_type": "voice",
  "display_name": "Voice Node",
  "health": {
    "id": "node.health",
    "kind": "health_strip",
    "title": "Health",
    "data_endpoint": "/api/node/ui/health",
    "refresh": {
      "mode": "near_live",
      "interval_ms": 15000
    }
  },
  "pages": [
    {
      "id": "overview",
      "title": "Overview",
      "page_endpoint": "/api/node/ui/pages/overview",
      "refresh": {
        "mode": "near_live",
        "interval_ms": 15000
      }
    }
  ]
}
```

Example page snapshot:

```json
{
  "page_id": "overview",
  "updated_at": "2026-05-13T09:46:27Z",
  "refresh": {
    "mode": "near_live",
    "interval_ms": 15000
  },
  "cards": [
    {
      "id": "node.warnings",
      "kind": "warning_banner",
      "data": {
        "kind": "warning_banner",
        "updated_at": "2026-05-13T09:46:27Z",
        "warnings": []
      }
    }
  ]
}
```

Example health response from `GET /api/node/ui/health`:

```json
{
  "kind": "health_strip",
  "updated_at": "2026-05-13T09:46:27Z",
  "items": [
    {
      "state_name": "Lifecycle",
      "current_state": "Operational",
      "tone": "success"
    }
  ]
}
```

Legacy per-surface manifest:

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
          "data_endpoint": "/api/node/ui/health",
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
