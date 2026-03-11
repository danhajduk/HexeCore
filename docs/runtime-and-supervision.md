# Runtime and Supervision

## Runtime Ownership

Status: Implemented

- Core owns desired-state intent and runtime orchestration hooks.
- Runtime boundaries execute concrete start/stop/rebuild/health flows.
- Supervisor/standalone runtime model remains active for standalone addon execution paths.

## Startup and Supervision

Status: Implemented

- Core startup initializes service stores, registry, MQTT manager/runtime boundary, and background supervision loops.
- MQTT runtime supervision handles unhealthy recovery and config-missing self-heal pathways.

## Scheduler and Worker Flow

Status: Implemented

- Job flow: submit -> lease request -> heartbeat -> complete/report/revoke.
- Queue APIs and history stats provide operational visibility.
- History cleanup and scheduler metrics are automated background concerns.

## Deployment and Runtime Boundaries

Status: Partial

- Deployment environment, paths, and service dependencies are defined in code and existing runbooks.
- Standalone vs embedded boundary behavior is implemented but still evolving.

## Store and Runtime Interaction

Status: Implemented

- Store lifecycle writes desired/runtime-linked state for addon deployment outcomes.
- Runtime status and diagnostics APIs expose deployment/runtime realization status.

## Planned

Status: Planned

- Further unification of standalone and embedded runtime observability surfaces.
- Additional runtime policy enforcement and lifecycle guardrails.

## See Also

- [Platform Architecture](./platform-architecture.md)
- [Core Platform](./core-platform.md)
- [Operators Guide](./operators-guide.md)
- [Data and State](./data-and-state.md)
