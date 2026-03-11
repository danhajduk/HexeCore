# Documentation Migration Summary

Date: 2026-03-11

## Scope Completed

Tasks 400-420 are completed.

### New Canonical Docs Created

- `docs/document-index.md`
- `docs/overview.md`
- `docs/platform-architecture.md`
- `docs/core-platform.md`
- `docs/addon-platform.md`
- `docs/mqtt-platform.md`
- `docs/runtime-and-supervision.md`
- `docs/auth-and-identity.md`
- `docs/data-and-state.md`
- `docs/api-reference.md`
- `docs/frontend-and-ui.md`
- `docs/operators-guide.md`
- `docs/development-guide.md`

### Migration Control Docs Created

- `docs/documentation-migration-map.md`
- `docs/documentation-migration-summary.md`

### Legacy Docs Archived

Superseded top-level legacy docs were moved to `docs/archive/` after content transfer.

Archived set includes:
- core/backend/api/addon/runtime/supervisor split docs
- MQTT split contracts/runbooks/gap notes
- theme/frontend split docs
- task-specific historical artifacts that are now represented in canonical docs

## Verification Notes

- Canonical API and subsystem claims were checked against:
  - `backend/app/main.py`
  - `backend/app/system/*/router.py`
  - `backend/app/api/*.py`
  - `frontend/src/core/router/routes.tsx`
- Canonical docs now label behavior as `Implemented`, `Partial`, `Planned`, or `Archived Legacy`.
- `docs/document-index.md` now acts as the docs front door and points to canonicals first.

## Result

The documentation set now has a single canonical navigation path, reduced overlap, and explicit archival of superseded files.
