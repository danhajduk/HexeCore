# Addon System Documentation

Last Updated: 2026-03-07 17:08 US/Pacific

## Core Perspective

Addon system includes discovery, registry, proxying, install-session orchestration, and standalone runtime intent handoff.

## Discovery and Registry

- discovery scans addon backend entrypoints in workspace addons directories
- registry stores loaded addons + registered remote addons
- registry endpoints exist for register/configure/verify flows
- service discovery supports service-provider registration through `POST /api/services/register`
  - registration fields: `service_type`, `addon_id`, `endpoint`, `health`, `capabilities`
  - service tokens are required (`aud=synthia-core`, scope `services.register`)
  - token subject must match `addon_id` and service entries are associated with addon registry metadata

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

## Health and Liveness Model

Implemented health states:
- `healthy`
- `unhealthy`
- `unknown`

State boundary:
- `runtime_state` describes container/runtime execution state.
- `health_status` describes service-level health from runtime metadata and optional health probing.

Optional probing behavior:
- Core runtime aggregation may probe `GET /api/addon/health` when probe is enabled and a published TCP port is available.
- Probing is optional and disabled by default (`SYNTHIA_RUNTIME_HEALTH_PROBE_ENABLED`).
- If endpoint is missing (`404`), `health_status` is `unknown`.

## UI Integration

- frontend includes addon inventory pages and dynamic addon route loading

## Platform Events Integration

Implemented lifecycle events emitted by core integrations:
- `service_registered` from `/api/services/register`
- `addon_installed` / `addon_updated` from store install/update success paths
- `addon_started` / `addon_failed` from MQTT announce/health transitions

Not developed:
- Guaranteed exactly-once delivery for addon lifecycle events
- Persistent historical lifecycle timeline beyond process memory

## Related Documents

- [supervisor.md](./supervisor.md)
- [standalone-addon.md](./standalone-addon.md)

## Not Developed

- Fully hot-reloadable embedded addon lifecycle without restart
- Universal policy enforcement for custom standalone compose files
