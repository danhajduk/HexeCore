# Core Environment Configuration

Status: Implemented

This file is generated from `docs/config/core-env-registry.json`.
Run `python tools/check_env_registry.py --write-docs` after intentional configuration changes.

Sensitive values are marked in the registry and must not be logged or exposed through public APIs.

## Auth and service access

| Name | Default | Sensitive | Description |
| --- | --- | --- | --- |
| `HEXE_ADMIN_COOKIE_SECURE` | `unset` | no | Controls admin login/session behavior or service-principal access. Registry key: `HEXE_ADMIN_COOKIE_SECURE`. |
| `HEXE_ADMIN_PASSWORD` | `unset` | yes | Initial seeded admin password; sensitive and used only for local account bootstrap. |
| `HEXE_ADMIN_SESSION_SECRET` | `unset` | yes | Secret used to sign admin browser sessions. |
| `HEXE_ADMIN_SESSION_TTL_SECONDS` | `unset` | no | Controls admin login/session behavior or service-principal access. Registry key: `HEXE_ADMIN_SESSION_TTL_SECONDS`. |
| `HEXE_ADMIN_TOKEN` | `unset` | yes | Bootstrap admin token and fallback seeded admin password when no explicit password is provided. |
| `HEXE_ADMIN_USERNAME` | `admin` | no | Controls admin login/session behavior or service-principal access. Registry key: `HEXE_ADMIN_USERNAME`. |
| `HEXE_CSRF_TRUSTED_ORIGINS` | `unset` | no | Controls admin login/session behavior or service-principal access. Registry key: `HEXE_CSRF_TRUSTED_ORIGINS`. |
| `HEXE_SERVICE_PRINCIPALS_JSON` | `unset` | yes | Controls admin login/session behavior or service-principal access. Registry key: `HEXE_SERVICE_PRINCIPALS_JSON`. |
| `HEXE_SERVICE_TOKEN` | `unset` | yes | Service token passed to standalone addon containers for Core callbacks. |
## Backend and frontend serving

| Name | Default | Sensitive | Description |
| --- | --- | --- | --- |
| `HEXE_API_BASE` | `unset` | no | Controls Core API binding, CORS, dashboard, or frontend static serving. Registry key: `HEXE_API_BASE`. |
| `HEXE_API_PORT` | `9001` | no | Controls Core API binding, CORS, dashboard, or frontend static serving. Registry key: `HEXE_API_PORT`. |
| `HEXE_BACKEND_HOST` | `127.0.0.1` | no | Controls Core API binding, CORS, dashboard, or frontend static serving. Registry key: `HEXE_BACKEND_HOST`. |
| `HEXE_BACKEND_PORT` | `9001` | no | Controls Core API binding, CORS, dashboard, or frontend static serving. Registry key: `HEXE_BACKEND_PORT`. |
| `HEXE_CORS_ALLOW_ORIGINS` | `unset` | no | Controls Core API binding, CORS, dashboard, or frontend static serving. Registry key: `HEXE_CORS_ALLOW_ORIGINS`. |
| `HEXE_DASHBOARD_URL` | `unset` | no | Controls Core API binding, CORS, dashboard, or frontend static serving. Registry key: `HEXE_DASHBOARD_URL`. |
| `HEXE_ENABLE_DEV_CORS` | `0` | no | Controls Core API binding, CORS, dashboard, or frontend static serving. Registry key: `HEXE_ENABLE_DEV_CORS`. |
| `HEXE_FRONTEND_DIST_DIR` | `unset` | no | Controls Core API binding, CORS, dashboard, or frontend static serving. Registry key: `HEXE_FRONTEND_DIST_DIR`. |
| `HEXE_SERVE_FRONTEND` | `1` | no | Controls Core API binding, CORS, dashboard, or frontend static serving. Registry key: `HEXE_SERVE_FRONTEND`. |
## Cloudflared and edge gateway

| Name | Default | Sensitive | Description |
| --- | --- | --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | `unset` | no | Cloudflare account ID accepted by the Edge Gateway settings flow. |
| `CLOUDFLARE_API_BASE` | `https://api.cloudflare.com/client/v4` | no | Controls Cloudflare API access or the repo-local/native cloudflared runtime. Registry key: `CLOUDFLARE_API_BASE`. |
| `CLOUDFLARE_API_TOKEN` | `unset` | yes | Cloudflare API token used for managed tunnel and DNS provisioning. |
| `CLOUDFLARE_ZONE_ID` | `unset` | no | Cloudflare zone ID accepted by the Edge Gateway settings flow. |
| `HEXE_CLOUDFLARED_BINARY` | `unset` | no | Controls Cloudflare API access or the repo-local/native cloudflared runtime. Registry key: `HEXE_CLOUDFLARED_BINARY`. |
| `HEXE_CLOUDFLARED_CONTAINER_NAME` | `hexe-cloudflared` | no | Controls Cloudflare API access or the repo-local/native cloudflared runtime. Registry key: `HEXE_CLOUDFLARED_CONTAINER_NAME`. |
| `HEXE_CLOUDFLARED_DOWNLOAD_URL` | `unset` | no | Controls Cloudflare API access or the repo-local/native cloudflared runtime. Registry key: `HEXE_CLOUDFLARED_DOWNLOAD_URL`. |
| `HEXE_CLOUDFLARED_IMAGE` | `cloudflare/cloudflared:latest` | no | Controls Cloudflare API access or the repo-local/native cloudflared runtime. Registry key: `HEXE_CLOUDFLARED_IMAGE`. |
| `HEXE_CLOUDFLARED_INSTALL_DIR` | `unset` | no | Controls Cloudflare API access or the repo-local/native cloudflared runtime. Registry key: `HEXE_CLOUDFLARED_INSTALL_DIR`. |
| `HEXE_CLOUDFLARED_PROVIDER` | `auto` | no | Controls Cloudflare API access or the repo-local/native cloudflared runtime. Registry key: `HEXE_CLOUDFLARED_PROVIDER`. |
| `HEXE_CLOUDFLARED_RESTART_POLICY` | `unless-stopped` | no | Controls Cloudflare API access or the repo-local/native cloudflared runtime. Registry key: `HEXE_CLOUDFLARED_RESTART_POLICY`. |
| `HEXE_CLOUDFLARED_SYSTEMD_UNIT` | `hexe-cloudflared.service` | no | Controls Cloudflare API access or the repo-local/native cloudflared runtime. Registry key: `HEXE_CLOUDFLARED_SYSTEMD_UNIT`. |
| `HEXE_CLOUDFLARED_VERSION` | `latest` | no | Controls Cloudflare API access or the repo-local/native cloudflared runtime. Registry key: `HEXE_CLOUDFLARED_VERSION`. |
| `HEXE_EDGE_RUNTIME_DIR` | `unset` | no | Controls Cloudflare API access or the repo-local/native cloudflared runtime. Registry key: `HEXE_EDGE_RUNTIME_DIR`. |
## Core runtime

| Name | Default | Sensitive | Description |
| --- | --- | --- | --- |
| `HEXE_CORE_RUNTIME_DECLARATIONS_JSON` | `unset` | no | Controls a Core runtime setting. Registry key: `HEXE_CORE_RUNTIME_DECLARATIONS_JSON`. |
| `HEXE_RUNTIME_HEALTH_PROBE_ENABLED` | `false` | no | Enables HTTP health probing for managed runtime endpoints. |
| `HEXE_RUNTIME_HEALTH_PROBE_TIMEOUT_S` | `2.0` | no | Timeout in seconds for managed runtime HTTP health probes. |
## Health, telemetry, and diagnostics

| Name | Default | Sensitive | Description |
| --- | --- | --- | --- |
| `HEXE_EVENTS_MAX_RECENT` | `200` | no | Controls health checks, telemetry sampling, or diagnostic retention. Registry key: `HEXE_EVENTS_MAX_RECENT`. |
| `HEXE_INTERNET_CHECK_HOST` | `1.1.1.1` | no | Controls health checks, telemetry sampling, or diagnostic retention. Registry key: `HEXE_INTERNET_CHECK_HOST`. |
| `HEXE_INTERNET_CHECK_PORT` | `53` | no | Controls health checks, telemetry sampling, or diagnostic retention. Registry key: `HEXE_INTERNET_CHECK_PORT`. |
| `HEXE_LOCAL_NETWORK_CHECK_HOST` | `unset` | no | Controls health checks, telemetry sampling, or diagnostic retention. Registry key: `HEXE_LOCAL_NETWORK_CHECK_HOST`. |
| `HEXE_LOCAL_NETWORK_CHECK_PORT` | `53` | no | Controls health checks, telemetry sampling, or diagnostic retention. Registry key: `HEXE_LOCAL_NETWORK_CHECK_PORT`. |
| `HEXE_SPEEDTEST_CLI_BIN` | `speedtest-cli` | no | Controls health checks, telemetry sampling, or diagnostic retention. Registry key: `HEXE_SPEEDTEST_CLI_BIN`. |
| `HEXE_SPEEDTEST_SAMPLE_SECONDS` | `1800` | no | Controls health checks, telemetry sampling, or diagnostic retention. Registry key: `HEXE_SPEEDTEST_SAMPLE_SECONDS`. |
| `HEXE_SPEEDTEST_TIMEOUT_S` | `45` | no | Controls health checks, telemetry sampling, or diagnostic retention. Registry key: `HEXE_SPEEDTEST_TIMEOUT_S`. |
| `HEXE_STACK_CONNECTIVITY_TTL_S` | `30` | no | Controls health checks, telemetry sampling, or diagnostic retention. Registry key: `HEXE_STACK_CONNECTIVITY_TTL_S`. |
## Install and update scripts

| Name | Default | Sensitive | Description |
| --- | --- | --- | --- |
| `HEXE_RAW_BASE_URL` | `https://raw.githubusercontent.com/danhajduk/HexeCore/main/core` | no | Controls install, bootstrap, or update script behavior. Registry key: `HEXE_RAW_BASE_URL`. |
| `HEXE_SKIP_CLOUDFLARED_NATIVE_INSTALL` | `0` | no | Controls install, bootstrap, or update script behavior. Registry key: `HEXE_SKIP_CLOUDFLARED_NATIVE_INSTALL`. |
| `HEXE_SUPERVISOR_PACKAGE_SOURCE_ROOT` | `repository root` | no | Local source tree used by Core to build Supervisor update packages when explicitly configured. |
| `HEXE_UPDATE_CLOUDFLARED_NATIVE` | `0` | no | Controls install, bootstrap, or update script behavior. Registry key: `HEXE_UPDATE_CLOUDFLARED_NATIVE`. |
## MQTT runtime and authority

| Name | Default | Sensitive | Description |
| --- | --- | --- | --- |
| `HEXE_MQTT_BOOTSTRAP_PORT` | `1884` | no | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `HEXE_MQTT_BOOTSTRAP_PORT`. |
| `HEXE_MQTT_DOCKER_CONTAINER` | `hexe-mqtt-broker` | no | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `HEXE_MQTT_DOCKER_CONTAINER`. |
| `HEXE_MQTT_DOCKER_IMAGE` | `eclipse-mosquitto:2` | no | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `HEXE_MQTT_DOCKER_IMAGE`. |
| `HEXE_MQTT_DOCKER_RESTART_POLICY` | `no` | no | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `HEXE_MQTT_DOCKER_RESTART_POLICY`. |
| `HEXE_MQTT_HOST` | `127.0.0.1` | no | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `HEXE_MQTT_HOST`. |
| `HEXE_MQTT_PORT` | `1883` | no | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `HEXE_MQTT_PORT`. |
| `HEXE_MQTT_RUNTIME_PROVIDER` | `docker` | no | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `HEXE_MQTT_RUNTIME_PROVIDER`. |
| `HEXE_MQTT_SESSION_IDLE_TIMEOUT_S` | `300` | no | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `HEXE_MQTT_SESSION_IDLE_TIMEOUT_S`. |
| `MQTT_AUTHORITY_AUDIT_DB` | `unset` | no | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `MQTT_AUTHORITY_AUDIT_DB`. |
| `MQTT_CREDENTIAL_STORE_PATH` | `unset` | yes | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `MQTT_CREDENTIAL_STORE_PATH`. |
| `MQTT_HOST` | `unset` | no | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `MQTT_HOST`. |
| `MQTT_INTEGRATION_STATE_DB` | `unset` | no | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `MQTT_INTEGRATION_STATE_DB`. |
| `MQTT_INTEGRATION_STATE_PATH` | `unset` | no | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `MQTT_INTEGRATION_STATE_PATH`. |
| `MQTT_LISTENER_ENABLED` | `true` | no | Enables the Core MQTT listener when MQTT broker configuration is available. |
| `MQTT_OBSERVABILITY_DB` | `unset` | no | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `MQTT_OBSERVABILITY_DB`. |
| `MQTT_PASSWORD` | `unset` | yes | MQTT password fallback read when settings storage has no saved password. |
| `MQTT_PORT` | `unset` | no | Controls MQTT broker runtime, credentials, authority state, or bootstrap ports. Registry key: `MQTT_PORT`. |
| `MQTT_USERNAME` | `unset` | no | MQTT username fallback read when settings storage has no saved username. |
## Node onboarding and governance

| Name | Default | Sensitive | Description |
| --- | --- | --- | --- |
| `HEXE_AI_NODE_ONBOARDING_APPROVAL_URL_BASE` | `unset` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_AI_NODE_ONBOARDING_APPROVAL_URL_BASE`. |
| `HEXE_AI_NODE_ONBOARDING_ENABLED` | `true` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_AI_NODE_ONBOARDING_ENABLED`. |
| `HEXE_AI_NODE_ONBOARDING_PROTOCOLS` | `1.0` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_AI_NODE_ONBOARDING_PROTOCOLS`. |
| `HEXE_BLE_PAIRING_SESSIONS_DB` | `data/ble_pairing_sessions.json` | no | Path for persisted BLE pairing session records used by the hardware onboarding flow. |
| `HEXE_BOOTSTRAP_ADVERTISE_HOST` | `unset` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_BOOTSTRAP_ADVERTISE_HOST`. |
| `HEXE_HARDWARE_ACCESS_DB` | `data/hardware_access.json` | no | Core persistence path for node hardware access requests, decisions, leases, releases, and audit metadata. |
| `HEXE_HARDWARE_LEASE_SECRET` | `unset` | yes | Shared secret used by Core to sign hardware access lease tokens and by Supervisor to validate them when Core lease validation is unavailable. |
| `HEXE_HARDWARE_LEASE_TTL_S` | `600` | no | Default lifetime in seconds for Core-issued hardware access leases. |
| `HEXE_NODE_ALLOWED_PROVIDERS` | `unset` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_ALLOWED_PROVIDERS`. |
| `HEXE_NODE_ALLOWED_TASK_FAMILIES` | `unset` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_ALLOWED_TASK_FAMILIES`. |
| `HEXE_NODE_GOVERNANCE_REFRESH_INTERVAL_S` | `120` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_GOVERNANCE_REFRESH_INTERVAL_S`. |
| `HEXE_NODE_ONBOARDING_APPROVAL_URL_BASE` | `unset` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_ONBOARDING_APPROVAL_URL_BASE`. |
| `HEXE_NODE_ONBOARDING_ARCHIVE_RETAIN_DAYS` | `30` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_ONBOARDING_ARCHIVE_RETAIN_DAYS`. |
| `HEXE_NODE_ONBOARDING_ENABLED` | `unset` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_ONBOARDING_ENABLED`. |
| `HEXE_NODE_ONBOARDING_PROTOCOLS` | `unset` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_ONBOARDING_PROTOCOLS`. |
| `HEXE_NODE_ONBOARDING_SUPPORTED_TYPES` | `ai-node,email-node,voice-node,interaction-node` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_ONBOARDING_SUPPORTED_TYPES`. |
| `HEXE_NODE_OPERATIONAL_MQTT_HOST` | `unset` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_OPERATIONAL_MQTT_HOST`. |
| `HEXE_NODE_OPERATIONAL_MQTT_PORT` | `unset` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_OPERATIONAL_MQTT_PORT`. |
| `HEXE_NODE_PROXY_TIMEOUT_SECONDS` | `10.0` | no | Timeout in seconds for proxied node UI/API upstream requests. |
| `HEXE_NODE_REAUTH_APPROVAL_URL_BASE` | `unset` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_REAUTH_APPROVAL_URL_BASE`. |
| `HEXE_NODE_RUNTIME_REFRESH_INTERVAL_SECONDS` | `5` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_RUNTIME_REFRESH_INTERVAL_SECONDS`. |
| `HEXE_NODE_SERVICE_TOKEN_TTL_S` | `600` | yes | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_SERVICE_TOKEN_TTL_S`. |
| `HEXE_NODE_STATUS_INACTIVE_AFTER_S` | `1800` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_STATUS_INACTIVE_AFTER_S`. |
| `HEXE_NODE_STATUS_STALE_AFTER_S` | `300` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_STATUS_STALE_AFTER_S`. |
| `HEXE_NODE_UI_HEALTH_TIMEOUT_SECONDS` | `2.0` | no | Timeout in seconds for node UI health probes before proxying browser traffic. |
| `HEXE_NODE_UI_MANIFEST_DEBUG_LOG` | `unset` | no | Controls node onboarding, reauth, trust bootstrap, governance, or capability filters. Registry key: `HEXE_NODE_UI_MANIFEST_DEBUG_LOG`. |
| `HEXE_NODE_UI_MANIFEST_REFRESH_AFTER_SECONDS` | `30.0` | no | Cache age in seconds after which Core refreshes a trusted node rendered-UI manifest in the background. |
| `HEXE_NODE_UI_MANIFEST_TIMEOUT_SECONDS` | `5.0` | no | Timeout in seconds for fetching a trusted node rendered-UI manifest. |
## Platform identity and branding

| Name | Default | Sensitive | Description |
| --- | --- | --- | --- |
| `HEXE_CORE_ID` | `hexe-core` | no | Controls platform display names, compatibility text, or stable Core identity. Registry key: `HEXE_CORE_ID`. |
| `HEXE_CORE_VERSION` | `0.1.0` | no | Controls platform display names, compatibility text, or stable Core identity. Registry key: `HEXE_CORE_VERSION`. |
| `PLATFORM_ADDONS_NAME` | `unset` | no | Controls platform display names, compatibility text, or stable Core identity. Registry key: `PLATFORM_ADDONS_NAME`. |
| `PLATFORM_CORE_NAME` | `unset` | no | Controls platform display names, compatibility text, or stable Core identity. Registry key: `PLATFORM_CORE_NAME`. |
| `PLATFORM_DOCS_NAME` | `unset` | no | Controls platform display names, compatibility text, or stable Core identity. Registry key: `PLATFORM_DOCS_NAME`. |
| `PLATFORM_DOMAIN` | `unset` | no | Controls platform display names, compatibility text, or stable Core identity. Registry key: `PLATFORM_DOMAIN`. |
| `PLATFORM_LEGACY_COMPATIBILITY_NOTE` | `unset` | no | Controls platform display names, compatibility text, or stable Core identity. Registry key: `PLATFORM_LEGACY_COMPATIBILITY_NOTE`. |
| `PLATFORM_LEGACY_INTERNAL_NAMESPACE` | `unset` | no | Controls platform display names, compatibility text, or stable Core identity. Registry key: `PLATFORM_LEGACY_INTERNAL_NAMESPACE`. |
| `PLATFORM_NAME` | `Hexe AI` | no | Controls platform display names, compatibility text, or stable Core identity. Registry key: `PLATFORM_NAME`. |
| `PLATFORM_NODES_NAME` | `unset` | no | Controls platform display names, compatibility text, or stable Core identity. Registry key: `PLATFORM_NODES_NAME`. |
| `PLATFORM_SHORT` | `unset` | no | Controls platform display names, compatibility text, or stable Core identity. Registry key: `PLATFORM_SHORT`. |
| `PLATFORM_SUPERVISOR_NAME` | `unset` | no | Controls platform display names, compatibility text, or stable Core identity. Registry key: `PLATFORM_SUPERVISOR_NAME`. |
## Store and addon runtime

| Name | Default | Sensitive | Description |
| --- | --- | --- | --- |
| `HEXE_ADDONS_DIR` | `../HexeAddons` | no | Controls addon store persistence, catalog trust material, or standalone addon runtime paths. Registry key: `HEXE_ADDONS_DIR`. |
| `HEXE_ADDON_PROXY_CIRCUIT_FAIL_THRESHOLD` | `3` | no | Failure count that opens the fallback addon proxy circuit when an addon does not provide per-addon proxy tuning. |
| `HEXE_ADDON_PROXY_CIRCUIT_OPEN_SECONDS` | `30` | no | Seconds the fallback addon proxy circuit remains open after repeated upstream failures. |
| `HEXE_ADDON_PROXY_RETRIES` | `1` | no | Fallback retry count for addon UI/API proxy upstream requests when an addon does not provide per-addon proxy tuning. |
| `HEXE_ADDON_PROXY_TIMEOUT_SECONDS` | `10.0` | no | Fallback timeout in seconds for addon UI/API proxy upstream requests when an addon does not provide per-addon proxy tuning. |
| `HEXE_CATALOG_PUBLISHERS` | `unset` | no | Controls addon store persistence, catalog trust material, or standalone addon runtime paths. Registry key: `HEXE_CATALOG_PUBLISHERS`. |
| `HEXE_CORE_URL` | `http://127.0.0.1:8000` | no | Controls addon store persistence, catalog trust material, or standalone addon runtime paths. Registry key: `HEXE_CORE_URL`. |
| `HEXE_SUPERVISOR_KEEP_VERSIONS` | `unset` | no | Controls addon store persistence, catalog trust material, or standalone addon runtime paths. Registry key: `HEXE_SUPERVISOR_KEEP_VERSIONS`. |
| `STORE_AUDIT_DB` | `unset` | no | Controls addon store persistence, catalog trust material, or standalone addon runtime paths. Registry key: `STORE_AUDIT_DB`. |
| `STORE_BACKUP_RETENTION` | `3` | no | Number of store data backups retained by lifecycle maintenance. |
| `STORE_CATALOG_MAX_BYTES` | `5000000` | no | Maximum downloaded byte size accepted for remote store catalogs. |
| `STORE_CATALOG_MAX_REDIRECTS` | `3` | no | Maximum redirect count followed while downloading remote store catalogs. |
| `STORE_CATALOG_PUBLIC_KEYS_JSON` | `unset` | no | Inline public publisher-key trust material for store catalog verification. |
| `STORE_CATALOG_PUBLIC_KEYS_PATH` | `var/store_catalog_public_keys.json` | no | Path to public publisher-key trust material for store catalog verification. |
| `STORE_CATALOG_TIMEOUT_S` | `12.0` | no | Timeout in seconds for downloading remote store catalogs. |
| `STORE_INSTALL_STATE_PATH` | `unset` | no | Path to persisted addon install/status metadata. |
| `STORE_SOURCES_DB` | `unset` | no | Path to store source configuration state. |
| `STORE_STAGING_TTL_MINUTES` | `60` | no | Minutes staged store packages are retained before lifecycle cleanup removes them. |
## Supervisor runtime

| Name | Default | Sensitive | Description |
| --- | --- | --- | --- |
| `HEXE_BLUETOOTH_ACCESS_POLICY` | `disabled` | no | Bluetooth access policy advertised by Supervisor and enforced by Core hardware access requests. Supported values: disabled, ask, trusted_only, allowed. |
| `HEXE_BLUETOOTH_ENSURE_POWERED` | `true` | no | When true, Supervisor attempts to keep detected Bluetooth adapters powered for host resource reporting and brokered Bluetooth access. |
| `HEXE_BLUETOOTH_POWER_RETRY_S` | `60` | no | Minimum seconds between Supervisor Bluetooth power-on retry attempts after a failed attempt. |
| `HEXE_CORE_SYSTEMD_UNIT` | `hexe-backend.service` | no | Systemd unit name that a local Supervisor reports and may inspect for the Core backend service. |
| `HEXE_HARDWARE_LEASE_VALIDATE_URL` | `unset` | no | Optional Core lease validation URL used by Supervisor hardware brokers. Defaults to HEXE_SUPERVISOR_CORE_URL plus /api/system/hardware/leases/validate. |
| `HEXE_SUPERVISOR_API_BASE_URL` | `unset` | no | HTTP base URL used by Core when the local Supervisor client is configured for HTTP transport. |
| `HEXE_SUPERVISOR_API_SOCKET` | `/run/hexe/supervisor.sock` | no | Unix socket path used by the local Supervisor API client when socket transport is enabled. |
| `HEXE_SUPERVISOR_API_SYSTEMD_UNIT` | `hexe-supervisor-api.service` | no | Systemd unit name that a local Supervisor reports and may inspect for the standalone Supervisor API service. |
| `HEXE_SUPERVISOR_API_TIMEOUT_S` | `unset` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_API_TIMEOUT_S`. |
| `HEXE_SUPERVISOR_API_TRANSPORT` | `socket` | no | Transport used by Core local Supervisor API client; expected values are socket, http, or disabled. |
| `HEXE_SUPERVISOR_BIND` | `127.0.0.1` | no | Bind address for the standalone Supervisor HTTP API when HTTP transport is enabled. |
| `HEXE_SUPERVISOR_BOOT_LOG` | `var/supervisor/boot.log` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_BOOT_LOG`. |
| `HEXE_SUPERVISOR_BOOT_POLL_S` | `2` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_BOOT_POLL_S`. |
| `HEXE_SUPERVISOR_BOOT_STEP_TIMEOUT_S` | `60` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_BOOT_STEP_TIMEOUT_S`. |
| `HEXE_SUPERVISOR_COMPOSE_RESTART_POLICY` | `no` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_COMPOSE_RESTART_POLICY`. |
| `HEXE_SUPERVISOR_CONTAINER_STATS_CACHE_S` | `unset` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_CONTAINER_STATS_CACHE_S`. |
| `HEXE_SUPERVISOR_CORE_HEARTBEAT_OFFLINE_S` | `unset` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_CORE_HEARTBEAT_OFFLINE_S`. |
| `HEXE_SUPERVISOR_CORE_HEARTBEAT_S` | `5` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_CORE_HEARTBEAT_S`. |
| `HEXE_SUPERVISOR_CORE_HEARTBEAT_STALE_S` | `unset` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_CORE_HEARTBEAT_STALE_S`. |
| `HEXE_SUPERVISOR_CORE_TOKEN` | `unset` | yes | Supervisor reporting token used for remote heartbeat, registration, and Core hardware lease validation calls. |
| `HEXE_SUPERVISOR_CORE_TOKEN_KIND` | `unset` | no | Header selector for Supervisor-to-Core authentication. Supported values are supervisor and admin. |
| `HEXE_SUPERVISOR_CORE_URL` | `unset` | no | Core API base URL used by remote Supervisor reporting and hardware lease validation. |
| `HEXE_SUPERVISOR_ENROLLMENT_TOKEN` | `unset` | yes | Enrollment token used by Supervisor install and registration flows. |
| `HEXE_SUPERVISOR_ENROLLMENT_TTL_S` | `900` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_ENROLLMENT_TTL_S`. |
| `HEXE_SUPERVISOR_FLEET_HISTORICAL_S` | `unset` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_FLEET_HISTORICAL_S`. |
| `HEXE_SUPERVISOR_FLEET_LOCAL_CACHE_S` | `10` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_FLEET_LOCAL_CACHE_S`. |
| `HEXE_SUPERVISOR_FLEET_OFFLINE_S` | `180` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_FLEET_OFFLINE_S`. |
| `HEXE_SUPERVISOR_FLEET_STALE_S` | `60` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_FLEET_STALE_S`. |
| `HEXE_SUPERVISOR_HISTORY_TIMEOUT_S` | `unset` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_HISTORY_TIMEOUT_S`. |
| `HEXE_SUPERVISOR_HOST_ID` | `hostname` | no | Host identifier reported by the standalone Supervisor API. |
| `HEXE_SUPERVISOR_ID` | `unset` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_ID`. |
| `HEXE_SUPERVISOR_INSTALL_MODE` | `unset` | no | Install mode selected by the Supervisor installer for local or remote service setup. |
| `HEXE_SUPERVISOR_INTERNET_CHECK_HOST` | `1.1.1.1` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_INTERNET_CHECK_HOST`. |
| `HEXE_SUPERVISOR_INTERNET_CHECK_PORT` | `53` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_INTERNET_CHECK_PORT`. |
| `HEXE_SUPERVISOR_INTERVAL_S` | `unset` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_INTERVAL_S`. |
| `HEXE_SUPERVISOR_LOCAL_AUX_UNITS` | `hexe-cloudflared.service,cloudflared.service` | no | Comma-separated auxiliary systemd units that a local Supervisor reports and may inspect. |
| `HEXE_SUPERVISOR_LOCAL_CORE` | `false` | no | Marks the Supervisor as co-located with Core so local runtime metadata is reported. |
| `HEXE_SUPERVISOR_LOG_LEVEL` | `INFO` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_LOG_LEVEL`. |
| `HEXE_SUPERVISOR_NAME` | `supervisor id` | no | Human-readable Supervisor name reported during install and resource reporting. |
| `HEXE_SUPERVISOR_NODE_HEARTBEAT_OFFLINE_S` | `180` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_NODE_HEARTBEAT_OFFLINE_S`. |
| `HEXE_SUPERVISOR_NODE_HEARTBEAT_STALE_S` | `60` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_NODE_HEARTBEAT_STALE_S`. |
| `HEXE_SUPERVISOR_NODE_SERVICE_ACTION_TIMEOUT_S` | `30` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_NODE_SERVICE_ACTION_TIMEOUT_S`. |
| `HEXE_SUPERVISOR_PORT` | `57665` | no | Port for the standalone Supervisor HTTP API when HTTP transport is enabled. |
| `HEXE_SUPERVISOR_PUBLIC_URL` | `unset` | no | Public or LAN-reachable Supervisor API URL reported to Core by the Supervisor. |
| `HEXE_SUPERVISOR_REPORT_ENABLED` | `true` | no | Enables periodic Supervisor resource and health reports when Core enrollment settings are present. |
| `HEXE_SUPERVISOR_REPORT_INTERVAL_S` | `15.0` | no | Interval in seconds between periodic Supervisor resource and health reports. |
| `HEXE_SUPERVISOR_REPORT_TIMEOUT_S` | `5.0` | no | Timeout in seconds for Supervisor resource and health report submissions. |
| `HEXE_SUPERVISOR_RESOURCE_HISTORY_PATH` | `unset` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_RESOURCE_HISTORY_PATH`. |
| `HEXE_SUPERVISOR_RESOURCE_HISTORY_PRUNE_INTERVAL` | `unset` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_RESOURCE_HISTORY_PRUNE_INTERVAL`. |
| `HEXE_SUPERVISOR_RESOURCE_HISTORY_PRUNE_INTERVAL_SECONDS` | `unset` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_RESOURCE_HISTORY_PRUNE_INTERVAL_SECONDS`. |
| `HEXE_SUPERVISOR_RESOURCE_HISTORY_RETENTION` | `unset` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_RESOURCE_HISTORY_RETENTION`. |
| `HEXE_SUPERVISOR_RESOURCE_HISTORY_RETENTION_SECONDS` | `unset` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_RESOURCE_HISTORY_RETENTION_SECONDS`. |
| `HEXE_SUPERVISOR_SOCKET` | `/run/hexe/supervisor.sock` | no | Unix socket path served by the standalone Supervisor API when socket transport is enabled. |
| `HEXE_SUPERVISOR_SUMMARY_CACHE_S` | `unset` | no | Controls Supervisor service identity, heartbeat windows, resource history, boot order, or host checks. Registry key: `HEXE_SUPERVISOR_SUMMARY_CACHE_S`. |
| `HEXE_SUPERVISOR_SYSTEMD_UNIT` | `hexe-supervisor.service` | no | Systemd unit name that a local Supervisor reports and may inspect for the Supervisor worker service. |
| `HEXE_SUPERVISOR_TRANSPORT` | `socket` | no | Transport served by the standalone Supervisor API; expected values are socket, http, or disabled. |
