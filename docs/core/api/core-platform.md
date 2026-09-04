# Core Platform

## Core Responsibilities

Status: Implemented

- Boot application and mount all subsystem routers.
- Own control-plane state and admin policy decisions.
- Coordinate addon registry, runtime status, and platform health aggregation.
- Coordinate embedded MQTT authority/runtime startup and reconciliation.
- Coordinate notification publisher, bridge, local consumer, and startup/debug notification flows.
- Expose canonical public naming metadata through `/api/system/platform`.

Code anchors:
- `backend/app/main.py`
- `backend/app/system/*`

## Setup / Readiness / Status Model

Status: Implemented

- Core tracks runtime setup/readiness for MQTT integration via integration state store.
- Setup summary and health/degraded API surfaces are exposed under `/api/system/mqtt/*`.
- Background supervision loop updates degraded/ready state and publishes audit/observability events.
- Core now allows the HTTP API to finish startup before the heavier MQTT authority warm-up sequence completes; MQTT reconcile and bootstrap publication continue in background startup warm-up tasks.

## Authority Boundaries

Status: Implemented

- Core is source of truth for:
  - admin users/session control
  - policy grants/revocations
  - MQTT principal authority state and effective access
- Runtime providers execute generated artifacts but do not own policy truth.

## Interaction With Runtime and Supervisor

Status: Partially implemented

- Core owns desired behavior and invokes runtime boundaries (`ensure_running`, `start`, `stop`, `rebuild`).
- Standalone runtime service and supervisor-related contracts remain active, with behavior segmented in runtime docs.

## Internal Scheduler

Status: Implemented

- Core hosts an internal recurring scheduler for Core-owned maintenance tasks.
- Core does not expose job queue, lease, worker, or job-history APIs.

## Known Legacy Context

Status: Implemented

- Prior supervisor/standalone mismatch analysis was transferred from task artifact docs and retained in archive for historical traceability.

## See Also

- [../../architecture.md](../../architecture.md)
- [Runtime and Supervision](../../supervisor/runtime-and-supervision.md)
- [Notifications Bus](../../mqtt/notifications.md)
- [API Reference](./api-reference.md)
- [Auth and Identity](./auth-and-identity.md)
