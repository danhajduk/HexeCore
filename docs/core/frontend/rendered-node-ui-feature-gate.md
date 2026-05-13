# Rendered Node UI Feature Gate

Status: Implemented

## Purpose

Rendered node UI is opt-in while nodes migrate from node-hosted operational UI to Core-owned UI. The legacy proxied iframe route remains available as fallback.

Implementation:

- `frontend/src/core/rendered-node-ui/featureGate.ts`
- `frontend/src/core/pages/RenderedNodeUiPage.tsx`
- `frontend/src/core/pages/NodeDetails.tsx`

## Gate Controls

The feature is enabled when either:

- `VITE_RENDERED_NODE_UI=true` at frontend build/runtime configuration
- browser local storage key `hexe.renderedNodeUi.enabled` is set to `true`, `1`, `yes`, `on`, or `enabled`

Local storage can also force-disable with `false`, `0`, `no`, `off`, or `disabled`.

Default state: disabled.

## Fallback

When disabled, `/nodes/:nodeId/rendered-ui` does not fetch the node manifest and offers the legacy route:

```text
/nodes/:nodeId/UI
```

Manifest load failures and invalid manifest states also preserve the legacy UI fallback link.

## Verification

Targeted tests:

```bash
cd frontend && npm test -- rendered-node-ui renderedNodeUiPage
```
