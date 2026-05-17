# Rendered Node UI Actions

Status: Implemented

## Purpose

Core executes rendered-node UI actions from manifest metadata. Card data may mark an action enabled or disabled, but executable endpoint and method information comes only from the validated manifest.

Implementation:

- `frontend/src/core/rendered-node-ui/api.ts`
- `frontend/src/core/pages/RenderedNodeUiPage.tsx`

## Behavior

The action layer:

- resolves card action ids against the active surface manifest `actions`
- rejects undeclared action ids
- confirms actions when manifest `confirmation.required=true`
- sends requests through Core-owned `/api/nodes/{node_id}/...` proxy paths
- refreshes the surface after a successful action
- displays success or error state next to the affected surface

Action execution currently supports manifest methods:

- `POST`
- `PUT`
- `PATCH`
- `DELETE`

## Verification

Targeted tests:

```bash
cd frontend && npm test -- rendered-node-ui renderedNodeUiPage
```
