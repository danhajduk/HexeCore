# BLE Onboarding Contract

Status: Implemented contract and broker route for `ble.provision_wifi`; physical GATT backend is pluggable and fails closed when unavailable
Last Updated: 2026-08-30

## Purpose

BLE onboarding gives an already trusted requester a narrow, Core-governed way to provision a nearby node over Bluetooth Low Energy without granting raw host Bluetooth, DBus, `/sys`, or privileged container access.

The first provisioning profile is the Voice node Wi-Fi/backend profile. The payload contract is node-profile extensible: other node types can publish their own provisioning payload schema while reusing the same BLE service, lease scope, pairing, status, and error model.

## Ownership Decisions

- Core owns requester authentication, policy, pairing nonce or claim-code validation, onboarding session binding, lease issuance, and persisted audit state.
- Supervisor owns host Bluetooth access and the brokered GATT client that talks to the target node.
- The target node owns the BLE peripheral GATT service and applies credentials locally.
- The requesting node/client supplies credentials to Supervisor only for the bounded provisioning operation. Core must not receive, persist, or log plaintext Wi-Fi credentials.
- The initial implementation uses a Supervisor pluggable GATT backend. It must fail closed when no backend is available.

## Security Decisions

- Operation name: `ble.provision_wifi`.
- Lease scope: `hardware.bluetooth.ble.provision_wifi`.
- Pairing nonce and claim code are single-use and bound to a Core onboarding session, target node identity, requester node identity, Supervisor id, and contract version.
- Nonces should expire quickly; the recommended default is 10 minutes.
- Credential protection is end-to-end at the provisioning envelope level before writing the `encrypted_credentials` characteristic. BLE link encryption is useful but not sufficient by itself.
- Secret-bearing payloads, ciphertext, plaintext Wi-Fi passwords, claim codes, and derived keys must not be logged or returned in API responses.

## GATT Service

Hexe BLE Onboarding Service UUID: `7f9c0000-5f04-4d8b-9a46-7c0f7a100000`

Characteristics:

- Device identity / board profile: `7f9c0001-5f04-4d8b-9a46-7c0f7a100000`
- Pairing nonce / claim code: `7f9c0002-5f04-4d8b-9a46-7c0f7a100000`
- Provisioning status: `7f9c0003-5f04-4d8b-9a46-7c0f7a100000`
- Encrypted credential write: `7f9c0004-5f04-4d8b-9a46-7c0f7a100000`
- Ack/error: `7f9c0005-5f04-4d8b-9a46-7c0f7a100000`

All JSON characteristic payloads use UTF-8 JSON. Binary encrypted payloads are base64url encoded inside JSON. Implementations should support chunking when BLE MTU limits require it.

## Characteristics

### Device Identity

Readable. Contains safe onboarding metadata only:

- `contract_version`
- `node_hardware_id`
- `board_profile`
- `firmware_version`
- `protocol_version`
- `supported_payload_schemas`
- `provisioning_state`

### Pairing Nonce

Readable and optionally notifiable. Contains:

- `onboarding_session_id`
- `target_node_id`
- `pairing_nonce`
- `claim_code_required`
- `expires_at`

Core validates nonce and claim-code freshness. Supervisor only brokers validation through Core or validates a Core-issued lease that carries the approved session binding.

### Provisioning Status

Readable and notifiable. Allowed states:

- `idle`
- `awaiting_credentials`
- `validating`
- `applying`
- `connected`
- `failed`
- `completed`

### Encrypted Credentials

Writable. Contains an encrypted provisioning envelope:

- `schema_version`
- `payload_schema_id`
- `contract_version`
- `onboarding_session_id`
- `target_node_id`
- `pairing_nonce`
- `algorithm`
- `key_id`
- `nonce`
- `ciphertext`

### Ack/Error

Readable and notifiable. Error codes:

- `invalid_nonce`
- `invalid_claim_code`
- `decrypt_failed`
- `unsupported_schema`
- `invalid_payload`
- `wifi_apply_failed`
- `backend_unreachable`
- `timeout`
- `already_provisioned`
- `gatt_backend_unavailable`

## Voice Payload Baseline

Voice node schema id: `hexe.voice_node.wifi_backend.v1`

Required fields:

- `wifi_ssid`
- `backend_host`
- `http_port`
- `ws_port`
- `use_tls`

Optional fields:

- `wifi_password`
- `endpoint_name`
- `display_name`

Validation:

- `wifi_ssid`: 1-32 characters.
- `wifi_password`: omit or null only for open networks; otherwise 8-63 characters.
- `backend_host`: hostname or IP address, 1-253 characters.
- `http_port`: integer, 1-65535.
- `ws_port`: integer, 1-65535.
- `use_tls`: boolean, default true.
- `endpoint_name`: optional stable endpoint key, 1-64 characters.
- `display_name`: optional operator-visible name, 1-80 characters.

## Schema Reference

Canonical schema catalog:

- [ble_onboarding_provisioning.schema.json](../json_schema/ble_onboarding_provisioning.schema.json)
