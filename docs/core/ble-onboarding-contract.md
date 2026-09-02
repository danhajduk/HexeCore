# BLE Onboarding Contract

Status: Implemented contract and broker route for `ble.provision_wifi`; physical GATT backend is pluggable and fails closed when unavailable
Last Updated: 2026-09-02

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
- GATT contract version: `1.0`.
- Provisioning envelope schema version: `1.0`.
- Pairing nonce and claim code are single-use and bound to a Core onboarding session, target node identity, requester node identity, Supervisor id, and contract version.
- Nonces should expire quickly; the recommended default is 10 minutes.
- Credential protection is end-to-end at the provisioning envelope level before writing the `encrypted_credentials` characteristic. BLE link encryption is useful but not sufficient by itself.
- Encryption uses the endpoint ephemeral X25519 public key and a Supervisor-generated ephemeral X25519 key. Both sides derive a one-use AES-256-GCM key with HKDF-SHA256.
- Replay protection is the pair of `sequence` and `expires_at`; endpoints must reject expired envelopes and already-seen sequence values for the active onboarding session.
- Secret-bearing payloads, ciphertext contents, plaintext Wi-Fi passwords, claim codes, derived keys, and decrypted payloads must not be logged or returned in API responses.

## Core Contract Authority

Core defines the canonical onboarding contract:

- `onboarding_session_id`: active Core onboarding session for this target.
- `target_node_id`: node id being provisioned.
- `pairing_nonce`: endpoint nonce read from the pairing characteristic.
- `claim_code_ref`: non-secret Core reference to a claim code that Core has already validated; Supervisor matches this reference from the Core-issued lease and must not log or require plaintext claim codes.
- `endpoint_ephemeral_public_key`: base64url-encoded raw X25519 endpoint public key read from the endpoint onboarding metadata.
- `contract_version`: `1.0`.
- `schema_version`: `1.0`.
- `sequence`: monotonically increasing integer within the onboarding session.
- `expires_at`: UTC ISO-8601 expiry for the pairing nonce and encrypted envelope.

Leases for `ble.provision_wifi` are scoped to `hardware.bluetooth.ble.provision_wifi` and bind the requester node, Supervisor, adapter, onboarding session, target node, endpoint public key, pairing nonce, claim-code reference, sequence, payload schema, and expiry window.

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
- `sequence`
- `expires_at`
- `algorithm`
- `key_agreement`
- `key_id`
- `supervisor_ephemeral_public_key`
- `nonce`
- `aad`
- `ciphertext`
- `tag`

The endpoint public key is carried in the Core-bound provisioning context, not inside the envelope written to GATT. `aad` is base64url-encoded canonical JSON of the non-secret envelope headers. `ciphertext` and `tag` are base64url-encoded AES-GCM output and must be treated as redacted operational data.

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
