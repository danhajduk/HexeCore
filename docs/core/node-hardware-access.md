# Node Hardware Access

Status: Implemented
Last Updated: 2026-08-30

## Purpose

Trusted nodes request host hardware through Core. Core owns policy decisions and short-lived leases. Supervisor owns host-local hardware observation and enforces leases through brokered APIs.

Bluetooth is the first implemented hardware resource. The current broker supports BLE status and BLE scan operations.

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

Example request:

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

Example Supervisor scan:

```http
POST /api/supervisor/hardware/bluetooth/ble/scan

{
  "node_id": "sensor-node-1",
  "lease_token": "<Core-issued lease token>",
  "adapter": "hci0",
  "scan_seconds": 5
}
```

## Policy

- `disabled`: all node Bluetooth access requests are denied.
- `ask`: requests are stored as pending until an admin approves or denies them.
- `trusted_only`: trusted nodes receive short-lived leases when Bluetooth is available.
- `allowed`: trusted nodes receive short-lived leases when Bluetooth is available.

Core fails closed when no online trusted Supervisor reports Bluetooth, when the hardware lease secret is missing, or when a lease is expired, released, or revoked.

## Supervisor Broker

Implemented BLE routes:

- `POST /api/supervisor/hardware/bluetooth/ble/status`
- `POST /api/supervisor/hardware/bluetooth/ble/scan`

Supervisor prefers Core validation using `HEXE_HARDWARE_LEASE_VALIDATE_URL` or `HEXE_SUPERVISOR_CORE_URL`. If Core validation is not configured, Supervisor can validate the signed lease locally with `HEXE_HARDWARE_LEASE_SECRET`; that mode cannot observe Core-side release state and is reported as `revocation_check=local_token_only`.

## Configuration

- `HEXE_BLUETOOTH_ACCESS_POLICY`: Bluetooth node access policy. Default: `disabled`.
- `HEXE_BLUETOOTH_ENSURE_POWERED`: Keep detected adapters powered. Default: `true`.
- `HEXE_BLUETOOTH_POWER_RETRY_S`: Power retry interval. Default: `60`.
- `HEXE_HARDWARE_ACCESS_DB`: Core hardware access state path. Default: `data/hardware_access.json`.
- `HEXE_HARDWARE_LEASE_SECRET`: shared Core/Supervisor lease signing secret. Required to grant leases.
- `HEXE_HARDWARE_LEASE_TTL_S`: default lease lifetime. Default: `600`.
- `HEXE_HARDWARE_LEASE_VALIDATE_URL`: optional explicit Core lease validation URL for Supervisor brokers.
