# Supervisor Service Configuration

This document describes the environment-backed configuration contract for the standalone Supervisor API service.

## Runtime Service Configuration

Supervisor can listen on a Unix socket (default) or a TCP bind/port. These options are configured entirely through environment variables so the service can run on any host without code changes.

## Environment Contract

- `HEXE_SUPERVISOR_TRANSPORT`: API transport mode. Supported values: `socket` or `http`. Default: `socket`.
- `HEXE_SUPERVISOR_BIND`: TCP bind host when `HEXE_SUPERVISOR_TRANSPORT=http`. Default: `127.0.0.1`.
- `HEXE_SUPERVISOR_PORT`: TCP port when `HEXE_SUPERVISOR_TRANSPORT=http`. Default: `57665`.
- `HEXE_SUPERVISOR_SOCKET`: Unix socket path when `HEXE_SUPERVISOR_TRANSPORT=socket`. Default: `/run/hexe/supervisor.sock`.
- `HEXE_SUPERVISOR_LOG_LEVEL`: Supervisor API server log level. Default: `INFO`.
- `HEXE_SUPERVISOR_NODE_SERVICE_ACTION_TIMEOUT_S`: timeout for proxied Node service start/stop/restart calls. Default: `30`.
- `HEXE_SUPERVISOR_BOOT_LOG`: Boot log file path (overwritten on Supervisor start). Default: `var/supervisor/boot.log`.
- `HEXE_SUPERVISOR_INSTALL_MODE`: install mode marker written by `scripts/install-supervisor.sh`. Supported installer values: `standalone`, `join-core`, and `bundled-core`.
- `HEXE_SUPERVISOR_ID`: stable ID for this host Supervisor when reporting to Core. Default: `<hostname>-supervisor`.
- `HEXE_SUPERVISOR_NAME`: display name for this host Supervisor. Default: `HEXE_SUPERVISOR_ID`.
- `HEXE_SUPERVISOR_PUBLIC_URL`: optional Core-reachable Supervisor API URL for remote detail/control flows.
- `HEXE_SUPERVISOR_CORE_URL`: Core API base URL used by remote Supervisor reporting. Reporting is disabled when unset.
- `HEXE_SUPERVISOR_CORE_TOKEN`: Supervisor reporting token used by remote Supervisor reporting. Compatibility installs may use a Core admin token when `HEXE_SUPERVISOR_CORE_TOKEN_KIND=admin`. Reporting is disabled when unset.
- `HEXE_SUPERVISOR_CORE_TOKEN_KIND`: token header selector for remote reporting. Supported values: `supervisor` for `X-Supervisor-Token` and `admin` for `X-Admin-Token`. The installer writes `supervisor` after exchanging a one-time enrollment token.
- `HEXE_SUPERVISOR_REPORT_ENABLED`: enables or disables remote reporting. Default: `true`.
- `HEXE_SUPERVISOR_REPORT_INTERVAL_S`: remote reporting interval. Default: `15`.
- `HEXE_SUPERVISOR_REPORT_TIMEOUT_S`: remote reporting request timeout. Default: `5`.

## Core Supervisor Client

Core talks to a remote Supervisor over the following environment-backed client settings.

- `HEXE_SUPERVISOR_API_TRANSPORT`: Client transport mode. Supported values: `socket`, `http`, or `disabled`. Default: `socket`.
- `HEXE_SUPERVISOR_API_BASE_URL`: Base URL for `http` transport. Default: `http://127.0.0.1:57665`.
- `HEXE_SUPERVISOR_API_SOCKET`: Unix socket path for `socket` transport. Default: `/run/hexe/supervisor.sock`.
- `HEXE_SUPERVISOR_API_TIMEOUT_S`: Client timeout (seconds). Default: `5.0`.
- `HEXE_SUPERVISOR_HISTORY_TIMEOUT_S`: Optional Core timeout for fleet-scoped remote Supervisor resource history reads. Defaults to `HEXE_SUPERVISOR_API_TIMEOUT_S` or `5.0`.
- `HEXE_CORE_RUNTIME_DECLARATIONS_JSON`: Optional JSON list (or `{ "items": [...] }`) of extra Core runtime declarations to register with the local Supervisor. Each entry should include `runtime_id`, `runtime_name`, `runtime_kind`, and `management_mode` plus optional state/metadata fields.
- `HEXE_BLUETOOTH_ACCESS_POLICY`: Bluetooth governance policy advertised by Supervisor when BT hardware is present. Supported values: `disabled`, `ask`, `trusted_only`, `allowed`. Default: `disabled`.
- `HEXE_BLUETOOTH_ENSURE_POWERED`: When true, Supervisor attempts to keep detected Bluetooth adapters powered. Default: `true`.
- `HEXE_BLUETOOTH_POWER_RETRY_S`: Minimum seconds between Bluetooth power-on retries after a failed attempt. Default: `60`.
- `HEXE_HARDWARE_LEASE_SECRET`: shared secret used to validate Core-issued hardware lease tokens. Required for local token validation and must match Core.
- `HEXE_HARDWARE_LEASE_VALIDATE_URL`: optional explicit Core lease validation URL for Supervisor hardware brokers. Defaults to `HEXE_SUPERVISOR_CORE_URL` plus `/api/system/hardware/leases/validate` when Core reporting is configured.
- `HEXE_SUPERVISOR_INTERNET_CHECK_HOST` / `HEXE_SUPERVISOR_INTERNET_CHECK_PORT`: Host and port used by each Supervisor to report local Internet reachability. Defaults: `1.1.1.1` and `53`.
- `HEXE_SUPERVISOR_FLEET_STALE_S`: Seconds after the latest Supervisor report before Core marks a fleet record `stale`. Default: `60`.
- `HEXE_SUPERVISOR_FLEET_OFFLINE_S`: Seconds after the latest Supervisor report before Core marks a fleet record `offline`. Default: `180`.
- `HEXE_SUPERVISOR_FLEET_HISTORICAL_S`: Seconds after the latest remote Supervisor report before Core hides a long-offline record from the default fleet list. Default: `604800` (7 days).
- `HEXE_SUPERVISOR_FLEET_LOCAL_CACHE_S`: Seconds Core may reuse the local attached Supervisor probe while serving fleet reads. Default: `10`.
- `HEXE_SUPERVISOR_RESOURCE_HISTORY_PATH`: Optional SQLite path for Supervisor-owned resource history. Default: `<repo>/data/supervisor_resource_history.sqlite3`.
- `HEXE_SUPERVISOR_RESOURCE_HISTORY_RETENTION`: Optional duration for resource history retention. Supports `s`, `m`, `h`, and `d` suffixes. Default: `3d`.
- `HEXE_SUPERVISOR_RESOURCE_HISTORY_RETENTION_SECONDS`: Legacy numeric override for resource history retention when the duration form is unset.
- `HEXE_SUPERVISOR_RESOURCE_HISTORY_PRUNE_INTERVAL`: Optional duration between history retention pruning passes. Supports `s`, `m`, `h`, and `d` suffixes. Default: `5m`.
- `HEXE_SUPERVISOR_RESOURCE_HISTORY_PRUNE_INTERVAL_SECONDS`: Legacy numeric override for the prune interval when the duration form is unset.

Resource history maintenance:

- `GET /api/supervisor/resources/history/maintenance` reports the SQLite path, DB/WAL/SHM sizes, row counts, retention, prune interval, free pages, and oldest/newest sample/event timestamps.
- `POST /api/supervisor/resources/history/maintenance` accepts `{"action":"prune"}`, `{"action":"checkpoint"}`, `{"action":"vacuum"}`, or `{"action":"compact"}`. `compact` is the normal operator action after a large history backlog: it applies retention pruning, truncates the WAL, and vacuums the DB while keeping the Supervisor process online.
- Use `checkpoint` when the WAL file is large but table counts are expected, `vacuum` after large deletes when free pages remain high, and `compact` when high Supervisor history latency was caused by an oversized `supervisor_resource_history.sqlite3`.

Bluetooth broker routes:

- `POST /api/supervisor/hardware/bluetooth/ble/status` validates a Core-issued hardware lease and returns adapter state.
- `POST /api/supervisor/hardware/bluetooth/ble/scan` validates a Core-issued hardware lease and runs a bounded BLE scan through Supervisor-managed `bluetoothctl`.

Bluetooth presence reporting does not grant node access. Nodes must request a Core hardware lease first; see [node-hardware-access.md](../core/node-hardware-access.md).

## Notes

- The Unix socket path is consistent across hosts to keep local Supervisor access predictable.
- When using `socket` transport, the Supervisor API server does not bind a TCP port.
- When using `http` transport, the Supervisor API server does not open a Unix socket.
- Remote Supervisor fleet visibility is push-based: each remote Supervisor posts registration and heartbeat payloads to Core at `/api/system/supervisors/register` and `/api/system/supervisors/heartbeat`.
- Preferred remote enrollment is one-time-token based. Core admins create a token at `POST /api/system/supervisors/enrollment-tokens`; the installing host exchanges it at `POST /api/system/supervisors/enroll`; the installer stores only the returned reporting token.
- `HEXE_SUPERVISOR_ENROLLMENT_TOKEN` is an installer input equivalent to `--enrollment-token` or `--one-time-token`. It is consumed during install and is not written to `supervisor.env`.

## Health And Readiness Probes

- `GET /health` returns a basic liveness response for the Supervisor API service.
- `GET /ready` returns readiness based on `execution_host_ready` from the Supervisor admission summary and responds with `503` when the host is not ready.
