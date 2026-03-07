# Addon System Documentation

## Core Perspective

Addon system includes discovery, registry, proxying, install-session orchestration, and standalone runtime intent handoff.

## Discovery and Registry

- discovery scans addon backend entrypoints in workspace addons directories
- registry stores loaded addons + registered remote addons
- registry endpoints exist for register/configure/verify flows

## Lifecycle (Core-Owned)

- addon install sessions:
  - start -> permissions approve -> deployment select -> configure -> verify
- store install flows for embedded/standalone package profiles
- standalone flow writes desired runtime intent and stages artifacts for supervisor

## Manifest Handling

- store and addon modules validate manifest/release structures and compatibility fields
- schema endpoint exposes canonical manifest schemas

## Runtime Intent Generation

- standalone desired state built via `standalone_desired.py`
- paths resolved via `standalone_paths.py`
- staged artifacts written under service version directories

## UI Integration

- frontend includes addon inventory pages and dynamic addon route loading

## Related Documents

- [supervisor.md](./supervisor.md)
- [standalone-addon.md](./standalone-addon.md)

## Not Developed

- Fully hot-reloadable embedded addon lifecycle without restart
- Universal policy enforcement for custom standalone compose files
