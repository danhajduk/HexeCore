# Documentation Migration Map

Last Updated: 2026-03-11 US/Pacific

This map classifies every top-level file in `docs/`, defines canonical ownership, and records migration actions.

## Classification Legend

- `canonical`: active primary reference
- `partial canonical`: useful but incomplete as a primary source
- `transitional`: migration bridge or design transition note
- `gap note`: explicit mismatch/missing-capability note
- `runbook`: operator procedure
- `task artifact`: task-specific audit/design output
- `legacy/replaceable`: superseded by newer canonical set

## Inventory (Top-Level `docs/`)

| Path | Type | Class | Overlap Domain | Migration Action | Canonical Target |
| --- | --- | --- | --- | --- | --- |
| `docs/New_tasks.txt` | task queue | task artifact | workflow | keep as-is | `docs/development-guide.md` (process link only) |
| `docs/Reasoning.txt` | reasoning log | task artifact | workflow | keep as-is | `docs/development-guide.md` (process link only) |
| `docs/completed.txt` | completion log | task artifact | workflow | keep as-is | `docs/development-guide.md` (process link only) |
| `docs/ROADMAP.md` | roadmap | partial canonical | planning | keep as-is and cross-link | `docs/overview.md`, `docs/development-guide.md` |
| `docs/addon-manifest.schema.json` | schema | canonical | addon/data | keep as-is and cross-link | `docs/data-and-state.md`, `docs/addon-platform.md` |
| `docs/desired.schema.json` | schema | canonical | runtime/data | keep as-is and cross-link | `docs/data-and-state.md`, `docs/runtime-and-supervision.md` |
| `docs/runtime.schema.json` | schema | canonical | runtime/data | keep as-is and cross-link | `docs/data-and-state.md`, `docs/runtime-and-supervision.md` |
| `docs/addon-system.md` | markdown | partial canonical | addon/core | archive after transfer | `docs/addon-platform.md` |
| `docs/addon-ui-styling.md` | markdown | partial canonical | frontend/theme/addon | archive after transfer | `docs/frontend-and-ui.md` |
| `docs/addons.md` | markdown | partial canonical | addon/core/api | archive after transfer | `docs/addon-platform.md` |
| `docs/api.md` | markdown | partial canonical | api/core/mqtt | archive after transfer | `docs/api-reference.md` |
| `docs/architecture-map.md` | markdown | transitional | architecture/core/backend | archive after transfer | `docs/platform-architecture.md`, `docs/overview.md` |
| `docs/auth-and-users.md` | markdown | partial canonical | auth/users | archive after transfer | `docs/auth-and-identity.md` |
| `docs/backend.md` | markdown | partial canonical | backend/core/api | archive after transfer | `docs/core-platform.md`, `docs/platform-architecture.md`, `docs/api-reference.md` |
| `docs/core.md` | markdown | partial canonical | architecture/index | archive after transfer | `docs/document-index.md`, `docs/core-platform.md` |
| `docs/data-model.md` | markdown | partial canonical | persistence/data | archive after transfer | `docs/data-and-state.md` |
| `docs/deployment.md` | markdown | partial canonical | runtime/deploy | archive after transfer | `docs/runtime-and-supervision.md`, `docs/operators-guide.md` |
| `docs/frontend.md` | markdown | partial canonical | frontend/ui | archive after transfer | `docs/frontend-and-ui.md` |
| `docs/mqtt-apply-rollback.md` | markdown | partial canonical | mqtt/runtime | archive after transfer | `docs/mqtt-platform.md`, `docs/operators-guide.md` |
| `docs/mqtt-authority-persistence.md` | markdown | transitional | mqtt/auth/data | archive after transfer | `docs/mqtt-platform.md`, `docs/auth-and-identity.md`, `docs/data-and-state.md` |
| `docs/mqtt-bootstrap-contract.md` | markdown | partial canonical | mqtt/bootstrap | archive after transfer | `docs/mqtt-platform.md` |
| `docs/mqtt-contract.md` | markdown | partial canonical | mqtt/api/core | archive after transfer | `docs/mqtt-platform.md`, `docs/api-reference.md` |
| `docs/mqtt-embedded-architecture.md` | markdown | transitional | mqtt/architecture | archive after transfer | `docs/mqtt-platform.md`, `docs/platform-architecture.md` |
| `docs/mqtt-embedded-contract.md` | markdown | transitional | mqtt/addon/core | archive after transfer | `docs/mqtt-platform.md`, `docs/addon-platform.md` |
| `docs/mqtt-embedded-gap-note.md` | markdown | gap note | mqtt migration | archive after transfer | `docs/mqtt-platform.md` |
| `docs/mqtt-observability.md` | markdown | partial canonical | mqtt/runtime | archive after transfer | `docs/mqtt-platform.md`, `docs/operators-guide.md` |
| `docs/mqtt-phase1-runbook.md` | markdown | runbook | mqtt ops | archive after transfer | `docs/operators-guide.md`, `docs/mqtt-platform.md` |
| `docs/mqtt-phase2-runbook.md` | markdown | runbook | mqtt ops | archive after transfer | `docs/operators-guide.md`, `docs/mqtt-platform.md` |
| `docs/mqtt-runtime-boundary.md` | markdown | partial canonical | mqtt/runtime | archive after transfer | `docs/mqtt-platform.md`, `docs/runtime-and-supervision.md` |
| `docs/mqtt-startup-reconciliation.md` | markdown | partial canonical | mqtt/startup | archive after transfer | `docs/mqtt-platform.md` |
| `docs/mqtt-topic-gap-note.md` | markdown | gap note | mqtt/topics | archive after transfer | `docs/mqtt-platform.md` |
| `docs/mqtt-topic-tree.md` | markdown | canonical | mqtt/topics | archive after transfer (folded into canonical MQTT doc) | `docs/mqtt-platform.md` |
| `docs/scheduler.md` | markdown | partial canonical | scheduler/runtime | archive after transfer | `docs/runtime-and-supervision.md`, `docs/platform-architecture.md` |
| `docs/standalone-addon.md` | markdown | partial canonical | addon/runtime | archive after transfer | `docs/addon-platform.md`, `docs/platform-architecture.md` |
| `docs/store.md` | markdown | partial canonical | addon/store/runtime | archive after transfer | `docs/addon-platform.md`, `docs/runtime-and-supervision.md`, `docs/api-reference.md` |
| `docs/supervisor-standalone-mismatch-report.md` | markdown | task artifact | supervisor/standalone | archive after transfer | `docs/core-platform.md`, `docs/platform-architecture.md` |
| `docs/supervisor.md` | markdown | partial canonical | supervisor/runtime | archive after transfer | `docs/runtime-and-supervision.md`, `docs/platform-architecture.md` |
| `docs/synthia_mqtt_addon_blueprint.md` | markdown | transitional | mqtt/addon architecture | archive after transfer | `docs/mqtt-platform.md` |
| `docs/task127-dashboard-audit.md` | markdown | task artifact | frontend/metrics | archive after transfer | `docs/frontend-and-ui.md` |
| `docs/task127-health-model.md` | markdown | task artifact | frontend/health | archive after transfer | `docs/frontend-and-ui.md`, `docs/operators-guide.md` |
| `docs/theme.md` | markdown | partial canonical | theme/frontend | archive after transfer | `docs/frontend-and-ui.md` |
| `docs/ui-theme.md` | markdown | partial canonical | theme/frontend | archive after transfer | `docs/frontend-and-ui.md` |
| `docs/worker_lifecycle.md` | markdown | partial canonical | scheduler/runtime | archive after transfer | `docs/runtime-and-supervision.md`, `docs/platform-architecture.md` |
| `docs/Policies/` | directory | canonical | policy references | leave in place and cross-link | `docs/development-guide.md`, `docs/document-index.md` |
| `docs/addon-store/` | directory | canonical | runbooks/spec | leave in place and cross-link | `docs/operators-guide.md`, `docs/api-reference.md` |
| `docs/distributed_addons/` | directory | canonical | distributed addons | leave in place and cross-link | `docs/addon-platform.md`, `docs/platform-architecture.md` |
| `docs/style_css_archive/` | directory | legacy/replaceable | theme/frontend | leave in place (historical assets) | `docs/frontend-and-ui.md` |
| `docs/archive/` | directory | canonical | archival | keep as-is | `docs/document-index.md` |

## Overlap Hotspots

### `mqtt*`

- Heavy overlap across contract, architecture target, runtime boundary, startup, observability, gap notes, and runbooks.
- Canonical consolidation target: `docs/mqtt-platform.md`.

### `addon*`

- Overlap between `addons.md`, `addon-system.md`, `standalone-addon.md`, and store/runtime docs.
- Canonical consolidation target: `docs/addon-platform.md`.

### `core` / `backend` / `api`

- Existing `core.md`, `backend.md`, and `api.md` duplicate ownership, route-group, and boundary definitions.
- Canonical consolidation targets: `docs/core-platform.md`, `docs/platform-architecture.md`, `docs/api-reference.md`.

### `supervisor` / `store` / `standalone`

- Runtime responsibilities split across `supervisor.md`, `deployment.md`, `store.md`, `standalone-addon.md`, and `worker_lifecycle.md`.
- Canonical consolidation target: `docs/runtime-and-supervision.md`.

### `theme` / `frontend` / `ui`

- Theming/UI integration split across `frontend.md`, `theme.md`, `ui-theme.md`, and `addon-ui-styling.md`.
- Canonical consolidation target: `docs/frontend-and-ui.md`.

## Canonical Ownership Map (New Files)

| Canonical File | Owns | Feeds From Existing Files |
| --- | --- | --- |
| `docs/document-index.md` | docs entrypoint, navigation, active vs archived map | `core.md`, `README.md`, migration map |
| `docs/overview.md` | system-level summary and platform model | `ROADMAP.md`, `architecture-map.md`, `core.md`, `backend.md`, MQTT architecture docs |
| `docs/platform-architecture.md` | subsystem architecture and boundaries | `architecture-map.md`, `core.md`, `backend.md`, `deployment.md`, `scheduler.md`, `supervisor.md`, `worker_lifecycle.md`, `standalone-addon.md` |
| `docs/core-platform.md` | Core control-plane behavior and authority boundaries | `core.md`, `backend.md`, `supervisor.md`, `supervisor-standalone-mismatch-report.md`, `scheduler.md` |
| `docs/addon-platform.md` | addon contracts, discovery, lifecycle, store coupling | `addons.md`, `addon-system.md`, `standalone-addon.md`, `store.md`, `distributed_addons/*` |
| `docs/mqtt-platform.md` | all MQTT architecture/authority/runtime/API/runbook topics | all `mqtt-*.md`, `synthia_mqtt_addon_blueprint.md` |
| `docs/auth-and-identity.md` | auth, users, principals, role boundaries | `auth-and-users.md`, `mqtt-authority-persistence.md`, `mqtt-contract.md`, `core.md` |
| `docs/data-and-state.md` | persistence files, schemas, state ownership | `data-model.md`, schema JSON files, `mqtt-authority-persistence.md` |
| `docs/api-reference.md` | endpoint reference grouped by subsystem | `api.md`, `backend.md`, `mqtt-contract.md`, backend route files |
| `docs/frontend-and-ui.md` | frontend architecture, addon UI integration, theming | `frontend.md`, `theme.md`, `ui-theme.md`, `addon-ui-styling.md` |
| `docs/runtime-and-supervision.md` | runtime ownership, supervision, scheduler/worker flow | `deployment.md`, `supervisor.md`, `scheduler.md`, `worker_lifecycle.md`, runtime sections of `store.md` |
| `docs/operators-guide.md` | setup, health checks, recovery and troubleshooting | `mqtt-phase1-runbook.md`, `mqtt-phase2-runbook.md`, `deployment.md`, runtime sections from MQTT docs |
| `docs/development-guide.md` | contribution workflow, docs maintenance, verification rules | `ROADMAP.md`, `Reasoning.txt`, `New_tasks.txt`, task artifacts |

## Migration Status

- Canonical structure defined: complete.
- New file ownership map defined: complete.
- Canonical docs authored: complete.
- Superseded legacy docs archived into `docs/archive/`: complete.
- Final migration summary recorded in `docs/documentation-migration-summary.md`: complete.
