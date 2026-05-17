# Addon Docs

This folder contains the canonical documentation for the Hexe AI addon subsystem.

## Included Docs

- [addon-platform.md](./addon-platform.md)
  High-level addon models, registry behavior, and store relationship.
- [addon-lifecycle.md](./addon-lifecycle.md)
  Code-verified install-session and runtime lifecycle reference.

## Scope

Status: Implemented

- Embedded addons are discovered and integrated into the Core runtime.
- External functionality is node-first in the migration structure.
- Standalone addon packaging and remediation documents live in `docs/addons/standalone-archive/` as compatibility and archival material tied to older store/runtime flows.

## Boundary Rules

- Use embedded addons for Core-local extension points that run inside the Core-managed runtime.
- Use Nodes for new external functionality, compute, or host-separated execution surfaces.
- Treat standalone addon runtime documents as archival or compatibility references unless a task explicitly requires that path.
- MQTT coordination for embedded addons remains part of the Core-owned messaging boundary.

## See Also

- [./embedded/README.md](./embedded/README.md)
- [./standalone-archive/README.md](./standalone-archive/README.md)
- [./standalone-archive/architecture.md](./standalone-archive/architecture.md)
