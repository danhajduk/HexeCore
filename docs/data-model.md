# Data Model Documentation

## Persistence Overview

Synthia uses mixed persistence:
- SQLite databases for durable structured system state
- JSON files for lightweight state/config documents

## SQLite-backed Data (Observed)

- App settings (`APP_SETTINGS_DB`, default `var/app_settings.db`)
- Users (`APP_USERS_DB`, default `var/users.db`)
- Scheduler history (`SCHEDULER_HISTORY_DB`, default `var/scheduler_history.db`)
- Scheduler queue persistence (`var/scheduler_queue.db`)
- Telemetry usage (`TELEMETRY_USAGE_DB`, default `var/telemetry_usage.db`)
- System stats samples (`data/system_stats.sqlite3`)
- Store audit (`STORE_AUDIT_DB`, default `var/store_audit.db`)

## JSON State and Config Files (Observed)

- Addon registry/state under `data/*.json`
- Install session state under `data/addon_install_sessions.json`
- Policy grants/revocations (`var/policy_*.json`)
- Store install state (`var/store_install_state.json` default)
- Store source metadata (`var/store_sources.json` default + runtime cache metadata)
- Standalone desired/runtime state (`SYNTHIA_ADDONS_DIR/services/<addon_id>/desired.json` and `runtime.json`)

## Ownership Boundaries

- Core backend owns settings/users/policy/store/scheduler records.
- Supervisor owns standalone `runtime.json` writes.
- Core store flow owns standalone `desired.json` writes and artifact staging.

## Not Developed

- Centralized schema registry for all JSON documents
- Migration framework that covers every JSON-backed state file
