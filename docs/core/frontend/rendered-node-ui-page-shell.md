# Rendered Node UI Page Shell

Status: Implemented

## Purpose

The rendered node UI page shell composes the Core-owned manifest loader, surface data loader, and shared card renderer registry into an operator page.

Route:

```text
/nodes/:nodeId/rendered-ui
```

The legacy proxied iframe route remains available at `/nodes/:nodeId/UI` as a fallback while rendered node UI is feature-gated.

## Behavior

The page shell:

- loads the validated manifest from `/api/nodes/{node_id}/ui-manifest`
- renders manifest pages as tabs
- loads surface data through Core-owned `/api/nodes/{node_id}/...` proxy paths
- renders surfaces through the shared card renderer registry
- enables polling only for `live` and `near_live` surfaces with explicit `interval_ms`
- resolves action ids through the manifest and executes confirmed actions through Core

## Verification

Targeted tests:

```bash
cd frontend && npm test -- rendered-node-ui renderedNodeUiPage
```
