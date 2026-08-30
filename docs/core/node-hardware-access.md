# Node Hardware Access

Status: Implemented
Last Updated: 2026-08-30

## Purpose

Trusted nodes request host hardware through Core. Core owns policy decisions and short-lived leases. Supervisor owns host-local hardware observation and enforces leases through brokered APIs.

Bluetooth is the first implemented hardware resource. The current broker supports BLE status and BLE scan operations. BLE Wi-Fi onboarding is specified separately in [BLE Onboarding Contract](./ble-onboarding-contract.md).

## Ownership

- Core authenticates the node, evaluates Supervisor-reported resource state, applies `HEXE_BLUETOOTH_ACCESS_POLICY`, records access requests, and issues leases.
- Supervisor detects Bluetooth adapters, optionally powers them, validates leases, and exposes a narrow BLE broker surface.
- Nodes do not receive raw host `/sys`, BlueZ DBus, privileged container, or host command access from Core.

## Node Request Flow

1. The node calls `POST /api/system/nodes/hardware/access-requests` with `X-Node-Trust-Token`.
2. Core confirms the node is trusted and selects an online Supervisor that reports `bluetooth_governance`.
3. Core returns one of:
   - `denied` when policy, trust, resource state, or lease signing prevents access
   - `pending` when policy is `ask`
   - `granted` with a short-lived `lease_id`, `lease_token`, `supervisor_id`, `broker_url`, and `expires_at`
4. The node calls the Supervisor broker with the lease token.
5. The node releases the lease with `POST /api/system/nodes/hardware/leases/{lease_id}/release`, or lets it expire.

## Core API

### Request Schema

`GET /api/system/nodes/hardware/access-requests/schema`

Authentication: none. This is a discovery endpoint for node clients.

Returns the JSON Schema for `POST /api/system/nodes/hardware/access-requests` plus the current hardware access schema version and supported resource/operation catalog.

```http
GET /api/system/nodes/hardware/access-requests/schema
```

Response fields:

- `schema_version`: current hardware access contract version.
- `resource_types`: currently `bluetooth`.
- `operations`: currently `ble.status` and `ble.scan`.
- `request_schema`: JSON Schema for the access request body. Unknown request fields are rejected.

### Request Access

`POST /api/system/nodes/hardware/access-requests`

Authentication: trusted node token in `X-Node-Trust-Token`.

Request fields:

- `node_id`: trusted node id. Required.
- `resource_type`: currently only `bluetooth`.
- `operation`: currently `ble.status` or `ble.scan`.
- `supervisor_id`: optional Supervisor id. When omitted, Core selects the first online trusted Supervisor that reports Bluetooth governance.
- `adapter`: optional adapter id such as `hci0`.
- `duration_s`: optional lease duration from 30 seconds to 24 hours. Default comes from `HEXE_HARDWARE_LEASE_TTL_S`.
- `reason`: optional operator-readable reason.

```http
POST /api/system/nodes/hardware/access-requests
X-Node-Trust-Token: <node trust token>

{
  "node_id": "sensor-node-1",
  "resource_type": "bluetooth",
  "operation": "ble.scan",
  "adapter": "hci0",
  "duration_s": 600,
  "reason": "discover nearby BLE sensors"
}
```

Granted response shape:

```json
{
  "ok": true,
  "access_request": {
    "request_id": "hwar_...",
    "node_id": "sensor-node-1",
    "resource_type": "bluetooth",
    "operation": "ble.scan",
    "supervisor_id": "office-supervisor",
    "adapter": "hci0",
    "status": "granted",
    "policy": "allowed",
    "lease_id": "hwlease_...",
    "lease_token": "<signed lease token>",
    "expires_at": "2026-08-30T16:00:00+00:00",
    "broker_url": "http://127.0.0.1:57665/api/supervisor/hardware/bluetooth/ble"
  }
}
```

Denied responses still return `200` with `status=denied` and a `decision_reason`; authentication and malformed requests use normal HTTP error codes.

### List Node Requests

`GET /api/system/nodes/{node_id}/hardware/access-requests`

Authentication: trusted node token in `X-Node-Trust-Token`.

Returns the node's hardware access requests and leases. Lease tokens are never returned from list endpoints.

### Release Lease

`POST /api/system/nodes/hardware/leases/{lease_id}/release`

Authentication: trusted node token in `X-Node-Trust-Token`.

```json
{
  "node_id": "sensor-node-1"
}
```

Release changes the persisted Core lease state to `released`. Supervisor can observe that state only when it validates leases through Core.

### Operator Review

`GET /api/system/hardware/access-requests`

Authentication: admin token/session.

Optional query:

- `status`: filter by `pending`, `granted`, `denied`, `released`, or `expired`.

`POST /api/system/hardware/access-requests/{request_id}/decision`

Authentication: admin token/session.

```json
{
  "decision": "approve",
  "duration_s": 600,
  "reason": "approved for nearby BLE sensor discovery"
}
```

The decision route applies to `pending` requests created under `HEXE_BLUETOOTH_ACCESS_POLICY=ask`.

### Lease Validation

`POST /api/system/hardware/leases/validate`

Authentication: admin token/session, or Supervisor reporting identity using `X-Supervisor-Id` and `X-Supervisor-Token`.

Supervisor uses this endpoint to validate the signed token and persisted Core lease state before brokered Bluetooth operations.

Request fields:

- `node_id`: trusted node id that owns the lease.
- `lease_token`: Core-issued signed hardware lease token.
- `resource_type`: currently only `bluetooth`.
- `operation`: currently `ble.status` or `ble.scan`.
- `supervisor_id`: optional Supervisor id to match against the lease.
- `adapter`: optional Bluetooth adapter id to match against the lease.

## Supervisor BLE API

All Supervisor BLE routes require a Core-issued lease token in the JSON body.

### BLE Status

`POST /api/supervisor/hardware/bluetooth/ble/status`

```json
{
  "node_id": "sensor-node-1",
  "lease_token": "<Core-issued lease token>",
  "adapter": "hci0"
}
```

Returns the selected adapter and all known adapters. The lease must include the `hardware.bluetooth.ble.status` scope.

### BLE Scan

`POST /api/supervisor/hardware/bluetooth/ble/scan`

```http
POST /api/supervisor/hardware/bluetooth/ble/scan

{
  "node_id": "sensor-node-1",
  "lease_token": "<Core-issued lease token>",
  "adapter": "hci0",
  "scan_seconds": 5
}
```

The lease must include the `hardware.bluetooth.ble.scan` scope. `scan_seconds` is bounded from 1 to 30 seconds. Supervisor runs the scan through `bluetoothctl --timeout <seconds> scan on`, then parses `bluetoothctl devices` output into BLE device rows.

Response fields include:

- `ok`: true when the broker request executed, false only for bounded runtime conditions such as missing `bluetoothctl`
- `operation`: `ble.scan`
- `node_id`
- `supervisor_id`
- `adapter`
- `adapters`
- `scan_seconds`
- `devices`: discovered rows with `address`, optional `name`, and `transport=ble`
- `revocation_check`: `core` or `local_token_only`

## Policy

- `disabled`: all node Bluetooth access requests are denied.
- `ask`: requests are stored as pending until an admin approves or denies them.
- `trusted_only`: trusted nodes receive short-lived leases when Bluetooth is available.
- `allowed`: trusted nodes receive short-lived leases when Bluetooth is available.

Core fails closed when no online trusted Supervisor reports Bluetooth, when the hardware lease secret is missing, or when a lease is expired, released, or revoked.

Current `trusted_only` and `allowed` behavior is intentionally the same after node authentication: both grant trusted nodes short-lived leases when Bluetooth is available. `trusted_only` is reserved for stricter trust-tier checks when the node trust model grows beyond the current trusted/untrusted distinction.

## Failure Modes

- `401 node_trust_token_required`: node route was called without `X-Node-Trust-Token`.
- `403 untrusted_node`: node token is invalid, revoked, or the registration is not trusted.
- `denied/bluetooth_supervisor_unavailable`: no online trusted Supervisor currently reports Bluetooth governance.
- `denied/bluetooth_policy_disabled`: the active Bluetooth policy is `disabled`.
- `denied/hardware_lease_secret_unconfigured`: Core cannot issue leases because `HEXE_HARDWARE_LEASE_SECRET` is unset.
- `403 hardware_access_*_mismatch`: the lease was presented by the wrong node, to the wrong Supervisor, for the wrong adapter, or for the wrong operation.
- `403 token_expired`: the signed lease token expired.
- `404 bluetooth_unavailable`: Supervisor no longer sees any Bluetooth adapter.
- `404 bluetooth_adapter_not_found`: the requested adapter id is not present.

## Supervisor Broker

Implemented BLE routes:

- `POST /api/supervisor/hardware/bluetooth/ble/status`
- `POST /api/supervisor/hardware/bluetooth/ble/scan`

Supervisor prefers Core validation using `HEXE_HARDWARE_LEASE_VALIDATE_URL` or `HEXE_SUPERVISOR_CORE_URL`. If Core validation is not configured, Supervisor can validate the signed lease locally with `HEXE_HARDWARE_LEASE_SECRET`; that mode cannot observe Core-side release state and is reported as `revocation_check=local_token_only`.

Core validation is the recommended production mode because it enforces release/revocation immediately. Local token-only validation should be treated as a fallback for standalone or disconnected Supervisor testing.

## Security Notes

- Keep `HEXE_HARDWARE_LEASE_SECRET` identical on Core and any Supervisor that may validate leases locally.
- Prefer Supervisor reporting tokens for Supervisor-to-Core lease validation; admin-token compatibility is for transitional installs.
- Do not give nodes direct BlueZ DBus, `/sys/class/bluetooth`, privileged container, or host command access as part of this flow.
- Bluetooth adapter power management is separate from access authorization. `bluetooth_present=true` or `bluetooth_powered=true` never means a node may use Bluetooth.
- Lease tokens are returned only at creation/approval time and are not persisted in plaintext.

## Configuration

- `HEXE_BLUETOOTH_ACCESS_POLICY`: Bluetooth node access policy. Default: `disabled`.
- `HEXE_BLUETOOTH_ENSURE_POWERED`: Keep detected adapters powered. Default: `true`.
- `HEXE_BLUETOOTH_POWER_RETRY_S`: Power retry interval. Default: `60`.
- `HEXE_HARDWARE_ACCESS_DB`: Core hardware access state path. Default: `data/hardware_access.json`.
- `HEXE_HARDWARE_LEASE_SECRET`: shared Core/Supervisor lease signing secret. Required to grant leases.
- `HEXE_HARDWARE_LEASE_TTL_S`: default lease lifetime. Default: `600`.
- `HEXE_HARDWARE_LEASE_VALIDATE_URL`: optional explicit Core lease validation URL for Supervisor brokers.
