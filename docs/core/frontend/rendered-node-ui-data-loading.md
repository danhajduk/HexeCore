# Rendered Node UI Data Loading

Status: Implemented

## Purpose

The Core frontend owns the data-loading layer for Core-rendered node UI. It loads validated manifests from Core, maps manifest data endpoints through Core-owned proxy paths, and exposes reloadable React hooks for later renderer components.

Implementation:

- `frontend/src/core/rendered-node-ui/api.ts`
- `frontend/src/core/rendered-node-ui/hooks.ts`
- `frontend/src/core/rendered-node-ui/types.ts`

## Manifest Loading

The frontend loads manifests through Core:

```http
GET /api/nodes/{node_id}/ui-manifest
```

The response is the server-validated `NodeUiManifestFetchResponse`. UI code must inspect `ok` and `status` before trying to render pages or surfaces.

## Surface Data Loading

Manifest `data_endpoint` values are node-local API paths such as:

```http
/api/node/ui/overview/health
```

The frontend data layer maps them to Core proxy paths:

```http
/api/nodes/{node_id}/node/ui/overview/health
```

Browser code must not call private node origins directly and must not accept absolute manifest endpoints.

## Hooks

`useNodeUiManifest(nodeId)` returns:

- `status`: `idle`, `loading`, `ready`, or `error`
- `data`: manifest fetch response, when available
- `error`: displayable failure text, when available
- `reload()`: explicit reload function

`useNodeSurfaceData(nodeId, endpoint)` returns the same load shape for a single surface data endpoint.

Renderer tasks should use these hooks instead of issuing direct `fetch()` calls.

## Verification

Targeted tests:

```bash
cd frontend && npm test -- rendered-node-ui
```
