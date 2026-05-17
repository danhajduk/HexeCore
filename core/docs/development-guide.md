# Development Guide

## Development Principles

Status: Implemented

- Keep behavior documentation code-verified.
- Prefer small, reviewable changes with targeted verification.
- Keep subsystem boundaries explicit (Core, addon, MQTT, runtime, UI).

## How To Extend Documentation

Status: Implemented

1. Update the relevant canonical doc first.
2. Add or adjust cross-links from `docs/index.md`.
3. Mark sections as `Implemented`, `Partial`, `Planned`, or `Archived Legacy`.
4. Archive superseded split docs only after content transfer is complete.

## How To Add Tasks

Status: Implemented

- Add new work to `docs/New_tasks.txt` in execution order.
- Keep task statements concrete and verifiable.
- Record completions in `docs/completed.txt` and `completed_task.txt`.

## How To Verify Docs Against Code

Status: Implemented

- Validate route claims from backend router files and `backend/app/main.py` mounts.
- Validate frontend claims from `frontend/src/core/router/routes.tsx` and related page components.
- Validate runtime/state claims from active service/store modules and schema files.

## Documentation Maintenance Note

Status: Implemented

- Prefer updating canonical docs over creating new overlapping top-level docs.
- Use `docs/archive/` only after useful content has been transferred.
- Keep planned vs implemented behavior clearly separated.
- Avoid one-off top-level docs unless they represent a durable reference.

## Planning Inputs

Status: Partial

- `docs/ROADMAP.md` remains an active planning input.
- `docs/Reasoning.txt` and task artifacts remain historical/operational context, not canonical architecture references.

## See Also

- [Document Index](./index.md)
- [Documentation Migration Map](./migration/documentation-migration-map.md)
- [Overview](./overview.md)
