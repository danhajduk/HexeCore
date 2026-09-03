# BLE Onboarding Contract

Status: Core-published pairing session lifecycle implemented; Supervisor BLE host-advert backend surface implemented
Last Updated: 2026-09-03

## Purpose

BLE onboarding gives an already trusted requester a narrow, Core-governed way to provision a nearby node over Bluetooth Low Energy without granting raw host Bluetooth, DBus, `/sys`, or privileged container access.

The first provisioning profile is the Voice node Wi-Fi/backend profile. The payload contract is node-profile extensible: other node types can publish their own provisioning payload schema while reusing the same BLE service, lease scope, pairing, status, and error model.

The preferred operator flow is Core-published pairing: the operator starts an
Add Device session, eligible Supervisors advertise the Hexe onboarding service,
and an unprovisioned endpoint discovers that advert, connects, and sends its
identity before credentials are released. The existing endpoint-advertises flow
remains a fallback/debug path for physical validation and recovery.

## Ownership Decisions

- Core owns requester authentication, policy, pairing nonce or claim-code validation, onboarding session binding, lease issuance, and persisted audit state.
- Supervisor owns host Bluetooth access and the brokered GATT client that talks to the target node.
- The target node owns the BLE peripheral GATT service and applies credentials locally.
- The requesting node/client supplies credentials to Supervisor only for the bounded provisioning operation. Core must not receive, persist, or log plaintext Wi-Fi credentials.
- The initial implementation uses a Supervisor pluggable GATT backend. It must fail closed when no backend is available.
- In Core-published pairing mode, Core owns the pairing session lifecycle,
  Supervisor owns the host BLE advertisement/GATT server, and the endpoint owns
  scanning, connecting, identity write, credential validation, and local apply.
- The endpoint `device_id` is the durable handoff key. It is sent during BLE
  identity exchange, approved by the operator, bound into the credential grant,
  and presented again when the endpoint comes online over Wi-Fi.

## Security Decisions

- Operation name: `ble.provision_wifi`.
- Lease scope: `hardware.bluetooth.ble.provision_wifi`.
- GATT contract version: `1.0`.
- Provisioning envelope schema version: `1.0`.
- Pairing nonce and claim code are single-use and bound to a Core onboarding session, target node identity, requester node identity, Supervisor id, and contract version.
- Core-published pairing sessions bind `device_id` and
  `onboarding_session_id` together. A Wi-Fi follow-up onboarding request is
  rejected if either value is missing, expired, already consumed, or different
  from the BLE-approved values.
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

This UUID block is reused for both directions. Implementations distinguish the
role in non-secret advert/session metadata:

- `endpoint_advert`: endpoint advertises, Supervisor scans/connects/reads.
- `host_pairing_advert`: Supervisor advertises a Core pairing session, endpoint
  scans/connects/writes identity.

Characteristics:

- Device identity / board profile: `7f9c0000-5f04-4d8b-9a46-7c0f7a100001`
- Pairing nonce / claim code: `7f9c0000-5f04-4d8b-9a46-7c0f7a100002`
- Provisioning status: `7f9c0000-5f04-4d8b-9a46-7c0f7a100003`
- Encrypted credential write: `7f9c0000-5f04-4d8b-9a46-7c0f7a100004`
- Ack/error: `7f9c0000-5f04-4d8b-9a46-7c0f7a100005`

All JSON characteristic payloads use UTF-8 JSON. Binary encrypted payloads are base64url encoded inside JSON. Implementations should support chunking when BLE MTU limits require it.

## Characteristics

### Device Identity

Endpoint-advert fallback mode: readable from the endpoint. Core-published
pairing mode: writable by the endpoint to the Supervisor host GATT service.
Contains safe onboarding metadata only:

- `contract_version`
- `device_id`
- `node_hardware_id`
- `target_node_id`
- `board_profile`
- `firmware_version`
- `application_type`
- `provisioning_mode`
- `protocol_version`
- `endpoint_ephemeral_public_key`
- `supported_payload_schemas`
- `provisioning_state`

### Pairing Nonce

Endpoint-advert fallback mode: readable and optionally notifiable from the
endpoint. Core-published pairing mode: readable from the Supervisor host GATT
service as a pairing offer. Contains:

- `onboarding_session_id`
- `target_node_id`
- `pairing_nonce`
- `claim_code_required`
- `expires_at`
- `session_role`
- `session_hint`

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

Endpoint-advert fallback mode: writable on the endpoint. Core-published pairing
mode: credentials are released only after the operator approves the BLE-reported
`device_id`; the endpoint must later present the same `device_id` and
`onboarding_session_id` over Wi-Fi before HexeVoice approval. Contains an
encrypted provisioning envelope:

- `schema_version`
- `payload_schema_id`
- `contract_version`
- `onboarding_session_id`
- `device_id`
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

## Core-Published Pairing Session

The Core-published pairing flow is the primary user-friendly onboarding path.
It avoids relying on a short-lived endpoint advert being visible at exactly the
same moment the operator scans.

1. Operator starts Add Device.
2. Core creates a short-lived `onboarding_session_id`.
3. Online Bluetooth-capable Supervisors advertise the Hexe onboarding service
   with `session_role=host_pairing_advert`.
4. The unprovisioned endpoint scans for the service UUID and role flag.
5. The endpoint connects to one advertising Supervisor and reads the pairing
   offer.
6. The endpoint writes device identity, including `device_id` and
   `board_profile`.
7. The UI asks the operator to approve that exact `device_id`.
8. Credentials are encrypted and released for that `device_id` and session.
9. The endpoint connects over Wi-Fi and starts HexeVoice onboarding with the
   same `device_id` and `onboarding_session_id`.
10. HexeVoice approves only that matching session/id pair, then consumes the
    pairing session.

### Advertisement Payload

The BLE advertisement must contain no secrets. Allowed fields:

- service UUID: `7f9c0000-5f04-4d8b-9a46-7c0f7a100000`
- `contract_version`
- `session_role`: `host_pairing_advert`
- short `session_hint`
- `expires_at` or compact expiry hint
- capability flags such as `voice_endpoint`

Forbidden in advertisements: Wi-Fi credentials, trust tokens, claim-code values,
pairing nonce values, endpoint private keys, long-lived Core secrets, and
plaintext credential payloads.

### Pairing Offer

The host GATT pairing offer contains non-secret, session-bound metadata:

- `contract_version`
- `onboarding_session_id`
- `session_role`: `host_pairing_advert`
- `session_hint`
- `supervisor_id`
- `core_id` or host identity hint
- `expires_at`
- `requested_profile`: `voice`
- `payload_schema_id`: `hexe.voice_node.wifi_backend.v1`
- `claim_code_required`

### Endpoint Identity Write

The endpoint identity write is required before credentials can be released:

- `contract_version`
- `onboarding_session_id`
- `device_id`
- `node_hardware_id`
- `target_node_id`
- `board_profile`
- `firmware_version`
- `application_type`
- `provisioning_mode`
- `endpoint_ephemeral_public_key`
- `supported_payload_schemas`
- `provisioning_state`

`device_id` must be stable across the BLE pairing phase and first Wi-Fi
onboarding request. The operator approves the device shown by this field.

### Wi-Fi Handoff

The endpoint stores the approved `onboarding_session_id` and `device_id` long
enough to complete first Wi-Fi onboarding. After receiving credentials and
joining Wi-Fi, it must include both values in its HexeVoice onboarding request.

HexeVoice/Core must reject the follow-up if:

- the session is unknown, expired, canceled, or already consumed
- the `device_id` does not match the BLE-approved identity
- the endpoint omits the session id or device id
- the board profile or payload schema is incompatible with the approved session

## Core/Supervisor Pairing APIs

Core exposes operator-owned BLE pairing sessions:

- `POST /api/system/hardware/bluetooth/ble/pairing-sessions`
- `GET /api/system/hardware/bluetooth/ble/pairing-sessions`
- `GET /api/system/hardware/bluetooth/ble/pairing-sessions/{session_id}`
- `POST /api/system/hardware/bluetooth/ble/pairing-sessions/{session_id}/approve`
- `POST /api/system/hardware/bluetooth/ble/pairing-sessions/{session_id}/cancel`

Supervisor exposes the brokered host-advert session surface used by Core:

- `POST /api/supervisor/hardware/bluetooth/ble/pairing-advert/start`
- `POST /api/supervisor/hardware/bluetooth/ble/pairing-advert/status`
- `POST /api/supervisor/hardware/bluetooth/ble/pairing-advert/stop`
- `POST /api/supervisor/hardware/bluetooth/ble/pairing-advert/endpoint-identity`

Core-issued pairing session tokens are scoped to
`hardware.bluetooth.ble.host_pairing_advert` and bind the Supervisor,
adapter, onboarding session id, session hint, expiry, and payload schema.
Supervisor strips tokens from status data before returning it. The default
Supervisor advert backend fails closed with
`ble_pairing_advert_backend_unavailable` until a host BLE GATT advertising
backend is configured.

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
