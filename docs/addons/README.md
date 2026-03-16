# Addon Docs

This folder contains the canonical documentation for the addon subsystem.

## Included Docs

- [addon-platform.md](./addon-platform.md)
  High-level addon models, registry behavior, and store relationship.
- [addon-lifecycle.md](./addon-lifecycle.md)
  Code-verified install-session and runtime lifecycle reference.

## Scope

Status: Implemented

- Embedded addons are discovered and integrated into the Core runtime.
- Standalone addons are lifecycle-managed by Core and realized through supervisor/runtime boundaries.
- Standalone addon packaging and remediation documents live in `docs/addons/standalone-archive/`.

## See Also

- [./embedded/README.md](./embedded/README.md)
- [./standalone-archive/README.md](./standalone-archive/README.md)
- [./standalone-archive/architecture.md](./standalone-archive/architecture.md)
