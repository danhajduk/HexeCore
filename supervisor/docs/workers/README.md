# Hexe Worker Docs

This folder is the worker landing page for execution helpers used with scheduled work in the Hexe AI platform.

## Status

Status: Partially implemented

- Worker support code is present under `backend/app/system/worker/`.
- Worker lifecycle and runner behavior are documented in the canonical worker runtime document.
- Current worker helpers act as scheduler clients, not as the Core scheduler ownership boundary.
- Host-local worker/process management should be read as Supervisor-owned runtime behavior during migration.
- Advanced worker fleet management is not verifiable from the current repository state.

## Current References

- [./worker-runtime.md](./worker-runtime.md)
- [../architecture.md](../architecture.md)
- [../fastapi/api-reference.md](../fastapi/api-reference.md)
- [../operators-guide.md](../operators-guide.md)
