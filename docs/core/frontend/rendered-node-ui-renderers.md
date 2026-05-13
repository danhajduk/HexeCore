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

## Action Rendering

Action-bearing cards render action controls from card data, but buttons remain disabled unless a Core action handler is passed in. Action execution is owned by a later action layer and must remain routed through Core.

## Verification

Targeted tests:

```bash
cd frontend && npm test -- rendered-node-ui
```
