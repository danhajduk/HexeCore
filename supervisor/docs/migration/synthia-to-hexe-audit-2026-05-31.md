# Synthia To Hexe Audit - 2026-05-31

Status: Task 957 inventory

This audit classifies remaining `synthia`, `Synthia`, and `SYNTHIA` references before the rename and compatibility tasks.

## Scan Summary

- Tracked source/docs/tests contain 1,897 case-insensitive `synthia` matches, excluding frontend build artifacts.
- Matches are mirrored across `core/` and `supervisor/`, so most implementation changes should be applied to both trees.
- Local env files contain `SYNTHIA_*` keys in `core/.config/hexe/admin.env` and `supervisor/.config/hexe/admin.env`. Secret values were not inspected or recorded.
- Path-level references still exist for `backend/synthia_supervisor`, `scripts/synthia.env.example`, `frontend/public/styles/synthia-core.css`, and several historical docs.

## Rename Now

- Backend logger names and source identifiers such as `synthia.core`, `synthia.system`, `synthia.addons`, `synthia.store`, `synthia.proxy`, `synthia.mqtt`, `synthia.events`, and `synthia.supervisor.client`.
- Environment variable primary names in runtime code, scripts, examples, and local env files, including admin/session, backend host/port, onboarding, node proxy/UI, logging, MQTT, addon proxy, store/addon runtime, Supervisor, Cloudflared, and stack health settings.
- Operator-facing defaults and runtime artifacts such as `/tmp/synthia_update.log`, `synthia_admin_session`, `synthia-updater.service`, `synthia-supervisor.service`, `synthia-frontend-dev.service`, `synthia-mqtt-broker`, `synthia-core`, and `synthia-debug-*`.
- Standalone addon package/runtime identifiers such as `synthia_supervisor`, `synthia-addon-*`, `synthia_net`, `SynthiaAddons`, `SYNTHIA_SERVICE_TOKEN`, and official catalog URLs using `Synthia-Addon-Catalog`.
- MQTT principal types and stored identities using `synthia_node` and `synthia_addon`, with a compatibility path for existing credentials and ACLs.
- UI/local browser keys such as `synthia_api_base`, `synthia_theme`, and the legacy stylesheet path `/styles/synthia-core.css`.
- Active docs, standards, schemas, fixtures, tests, and task details where Synthia is still presented as the canonical product name.

## Migrate With Compatibility

- `SYNTHIA_*` environment variables should become `HEXE_*` primary names while preserving fallback reads for existing installs until a documented removal window.
- Admin cookies and local storage keys should prefer Hexe names but read or migrate existing Synthia keys so active sessions and browser settings are not stranded.
- MQTT principal types, ACL subjects, topic roots, and credential records should accept legacy `synthia_node`, `synthia_addon`, and `synthia` values while new records use Hexe names.
- Docker compose project names, network names, container names, service tokens, and addon runtime paths should create Hexe defaults but continue to discover existing Synthia artifacts.
- The Python package rename from `synthia_supervisor` to `hexe_supervisor` should keep a temporary import alias or wrapper so old scripts/tests fail gracefully only after migration coverage exists.
- Public URLs, generated manifests, and store catalog references should prefer Hexe endpoints while documenting whether the old Synthia catalog remains a legacy source alias.

## Intentional Legacy Or Archive

- `docs/archive/**`, historical migration reports, and older task-detail rationale can keep Synthia references when they are explicitly historical.
- Compatibility tests should keep Synthia strings while proving legacy env/config/data continues to load.
- Comments that label a fallback as legacy are allowed, but should not describe Synthia as the active brand.

## Local Env Keys Found

The following keys appear in both `core/.config/hexe/admin.env` and `supervisor/.config/hexe/admin.env`; values are intentionally omitted:

- `SYNTHIA_ADMIN_TOKEN`
- `SYNTHIA_BACKEND_HOST`
- `SYNTHIA_BACKEND_PORT`
- `SYNTHIA_AI_NODE_ONBOARDING_APPROVAL_URL_BASE`
- `SYNTHIA_LOG_ADDONS_LEVEL`
- `SYNTHIA_LOG_API_LEVEL`
- `SYNTHIA_LOG_CORE_LEVEL`
- `SYNTHIA_LOG_SYSTEM_LEVEL`
- `SYNTHIA_CORE_VERSION`
- `SYNTHIA_LOG_STORE_LEVEL`

## High-Risk Areas For Tasks 958-963

- `backend/app/api/admin.py`: auth env names, cookie name, updater service unit, and update log path.
- `backend/app/system/mqtt/**`: principal type literals, credential stores, ACL rendering, default client ids, topic roots, and runtime container defaults.
- `backend/app/store/**` and `backend/synthia_supervisor/**`: standalone addon runtime paths, compose metadata, package imports, default networks, and service-token env injection.
- `backend/app/api/system.py` and node services: onboarding and node-governance env names plus persisted principal type values.
- `scripts/*.sh`, `systemd/user/*.in`, `.config/hexe/*.env`, and `scripts/synthia.env.example`: install/update/runtime environment and service artifact names.
- Frontend storage and static assets: local storage keys and legacy stylesheet names.

