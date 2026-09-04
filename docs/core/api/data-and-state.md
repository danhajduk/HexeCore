# Data and State

## Persistent State Overview

Hexe Core persists control-plane state in SQLite and JSON documents.

Status: Implemented

## SQLite Stores

Status: Implemented

Observed active stores include:
- app settings (`APP_SETTINGS_DB`, default `var/app_settings.db`)
- users (`APP_USERS_DB`, default `var/users.db`)
- scheduler history (`SCHEDULER_HISTORY_DB`, default `var/scheduler_history.db`)
- telemetry usage (`TELEMETRY_USAGE_DB`, default `var/telemetry_usage.db`)
- MQTT authority audit/observability stores
- store audit persistence

## JSON State Files

Status: Implemented

Observed JSON-backed state includes:
- MQTT integration state (`var/mqtt_integration_state.json`)
- MQTT credential store (`var/mqtt_credentials.json`)
- node onboarding session state (`data/node_onboarding_sessions.json`)
- node onboarding archived terminal sessions (`data/node_onboarding_sessions.json.archive.jsonl`)
- global node registrations (`data/node_registrations.json`)
- node capability profiles (`data/node_capability_profiles.json`)
- node governance bundles (`data/node_governance_bundles.json`)
- AI Node trust issuance records (`data/node_trust_records.json`)
- policy grants/revocations (`var/policy_*.json`)
- service catalog and store source state
- standalone addon desired/runtime files

## Node Capability Store Compatibility

Status: Implemented

Node capability migration is lazy and load-time only. Operators should not hand-edit live JSON as the primary migration path.

Current behavior:

- legacy registration records using `declared_capabilities[]` or `declared_task_families[]` load as provider-side `provided_task_families[]`
- legacy capability profile records using old provider declarations load as provider-side `provided_task_families[]`
- missing `requested_task_families[]` loads as an empty requester dependency list
- explicit empty `provided_task_families[]` is preserved for requester-only records
- new saves include distinct provider and requester fields
- governance bundles are regenerated through the normal current-governance path when profile-derived routing constraints change

## Desired and Runtime Models

Status: Implemented

- Desired/runtime schema references:
  - [`store.standalone-desired.models.schema.json`](../../json_schema/store.standalone-desired.models.schema.json)
  - [`runtime.models.schema.json`](../../json_schema/runtime.models.schema.json)
- Core writes desired intent for runtime realization.
- Supervisor/runtime layers realize runtime state.
- Historical SSAP v1 standalone-addon schemas remain archived under
  [`docs/addons/standalone-archive/`](../../addons/standalone-archive/README.md)
  and are not the current Core-owned desired/runtime model contracts.

## Addon Manifest Model

Status: Implemented

- Canonical schema: [`addons.models.schema.json`](../../json_schema/addons.models.schema.json)
- Used by store/addon lifecycle validation and metadata handling.

## Authority State

Status: Implemented

- MQTT authority state includes setup/readiness fields, grants, and principal maps.
- Runtime-generated artifacts are derived outputs; authority JSON/DB state remains source of truth.

## Schema Ownership

Status: Implemented

- JSON schemas in `docs/json_schema/` are canonical references for contract shape.
- Canonical docs reference schemas rather than duplicating full schema bodies.
- Historical schemas under `docs/addons/standalone-archive/` document the legacy
  standalone-addon protocol only.

## Planned

Status: Not developed

- Unified migration framework for all JSON and SQLite contract evolution.
- Centralized schema registry with versioned cross-subsystem compatibility checks.

## See Also

- [Core Platform](./core-platform.md)
- [Runtime and Supervision](../../supervisor/runtime-and-supervision.md)
- [MQTT Platform](../../mqtt/mqtt-platform.md)
- [Addon Platform](../../addons/addon-platform.md)
