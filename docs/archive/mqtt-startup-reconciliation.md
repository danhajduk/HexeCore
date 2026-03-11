# Archived Document

Status: Outdated
Replaced by: docs/document-index.md (canonical set)
Preserved for historical reference only.

# MQTT Startup Reconciliation (Embedded)

Last Updated: 2026-03-09 09:01 US/Pacific

## Implementation

Core startup reconciler:
- `backend/app/system/mqtt/startup_reconcile.py`

Wiring:
- `backend/app/main.py` startup flow invokes reconciler after MQTT manager start.
- `backend/app/main.py` also runs a periodic runtime supervision loop to keep the broker running and mark setup state degraded if runtime health drops.

## Startup Flow

On startup the reconciler:
1. loads Core MQTT authority state
2. compiles ACL artifacts
3. renders broker config artifacts
4. renders broker credentials (`passwords.conf`) from Core MQTT principals
5. applies staged artifacts through apply pipeline
6. checks runtime readiness through runtime boundary
7. updates setup state (`ready` or `degraded`)
8. publishes retained bootstrap/core info topics when healthy
9. retries bootstrap publish from supervision loop until at least one publish succeeds

## Degraded Handling

- Reconcile errors are captured as degraded/error state.
- Audit events are written for startup reconcile outcomes.
- Runtime supervision writes degraded setup state and runtime-health audit events when broker health checks fail.
