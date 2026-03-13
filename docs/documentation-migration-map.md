# Documentation Migration Map

This document records the current documentation normalization state for the repository.

## Current Canonical Entry Points

- `docs/index.md`
- `docs/overview.md`
- `docs/architecture.md`

## Recent Consolidations

- `document-index.md` was merged into `docs/index.md` and archived.
- `platform-architecture.md` was merged into the `overview` and `architecture` docs and archived.
- Distributed addon docs were folded into the standalone addon area.
- AI-node-specific docs were moved into `docs/temp-ai-node/`.
- `Policies/` was renamed to `standards/`.

## Active Subsystem Folders

- `docs/fastapi/`
- `docs/frontend/`
- `docs/mqtt/`
- `docs/addons/`
- `docs/addon-embedded/`
- `docs/addon-standalone/`
- `docs/nodes/`
- `docs/temp-ai-node/`
- `docs/scheduler/`
- `docs/workers/`
- `docs/supervisor/`

## Notes

- `docs/archive/` remains historical reference material and is ignored for future workflow state.
- `docs/reports/` contains audit artifacts rather than canonical subsystem documentation.
