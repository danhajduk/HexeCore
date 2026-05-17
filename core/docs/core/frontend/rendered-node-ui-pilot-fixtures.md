# Rendered Node UI Pilot Fixtures

Status: Implemented

## Purpose

Pilot fixtures provide a reference manifest and card payload set for the initial Core-rendered node UI card kinds. They keep backend contracts, frontend endpoint routing, renderer coverage, and action routing aligned while real node implementations migrate.

Backend fixtures:

- `backend/tests/fixtures/node_ui_pilot.py`

Frontend fixtures:

- `frontend/src/core/rendered-node-ui/pilotFixtures.ts`

## Coverage

The pilot fixtures cover:

- manifest fetch and validation
- every initial shared card kind
- data endpoint mapping through Core
- action endpoint mapping through Core
- renderer registry coverage

## Verification

Backend:

```bash
cd backend && .venv/bin/python -m pytest tests/test_node_ui_manifest.py tests/test_node_ui_card_contracts.py tests/test_node_ui_manifest_fetch_service.py tests/test_node_ui_pilot_fixtures.py
```

Frontend:

```bash
cd frontend && npm test -- rendered-node-ui renderedNodeUiPage
```
