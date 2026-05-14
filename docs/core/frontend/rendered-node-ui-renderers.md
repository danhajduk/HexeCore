# Rendered Node UI Renderers

Status: Implemented

## Purpose

Core owns rendered node UI presentation. Nodes provide validated card data; frontend renderer components decide layout, tone styling, empty states, stale states, and unsupported-card behavior.

Implementation:

- `frontend/src/core/rendered-node-ui/renderers.tsx`
- `frontend/src/core/rendered-node-ui/rendered-node-ui.css`

## Renderer Registry

`NODE_UI_CARD_RENDERERS` maps manifest/card `kind` values to Core-owned React components.

Initial renderer kinds:

- `node_overview`
- `health_strip`
- `facts_card`
- `warning_banner`
- `action_panel`
- `runtime_service`
- `provider_status`

Unknown card kinds render a safe unsupported state instead of executing node-provided UI code.

## Runtime Service Cards

`runtime_service` renders each service as a compact clickable tile with the service label, state, and short provider/model summary. Opening a tile shows the full Core-owned details dialog with facts, resource usage, errors, and service-level actions such as start, stop, and restart when the node advertises matching action metadata.

## Provider Status Cards

`provider_status` renders each provider as a compact clickable tile with the provider label, state, and short provider/status summary. Opening a tile shows a Core-owned details dialog split into `Status` and `Setup` sections. Nodes can use `facts`, `quotas`, and `errors` for status details, and optional `setup.facts`, `setup.errors`, and `setup.actions` for reusable provider setup state.

## Action Rendering

Action-bearing cards render action controls from card data, but buttons remain disabled unless a Core action handler is passed in. Action execution is routed through the Core action layer, which resolves executable metadata from the manifest.

## Verification

Targeted tests:

```bash
cd frontend && npm test -- rendered-node-ui
```
