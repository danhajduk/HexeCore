# Rendered Node UI Advertisement Gate

Status: Implemented

## Purpose

Rendered node UI is enabled per node when that node advertises a valid Core-rendered UI manifest. The legacy proxied iframe route remains available as fallback.

Implementation:

- `frontend/src/core/pages/NodeDetails.tsx`
- `frontend/src/core/pages/RenderedNodeUiPage.tsx`
- `frontend/src/core/rendered-node-ui/hooks.ts`

## Gate Behavior

Node details checks `GET /api/nodes/{node_id}/ui-manifest` for trusted nodes.

If Core returns `ok: true`, the node has advertised the new Core-rendered UI and the **Open Core UI** entrypoint is enabled.

If Core returns any other state, the Core UI entrypoint is disabled and exposes the manifest failure reason as the button tooltip.

## Fallback

`/nodes/:nodeId/rendered-ui` also fetches the manifest directly. Manifest load failures and invalid manifest states preserve the legacy UI fallback link:

```text
/nodes/:nodeId/UI
```

## Verification

Targeted tests:

```bash
cd frontend && npm test -- rendered-node-ui renderedNodeUiPage
```
