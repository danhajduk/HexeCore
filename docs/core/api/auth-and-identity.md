# Auth and Identity

## Identity Domains

### Admin Users

Status: Implemented

- Human users support `owner`, `admin`, `member`, and `guest` roles.
- The existing `Dan` administrator is migrated in place to the initial owner;
  the seeded `admin` account remains an administrator.
- User CRUD is exposed under admin APIs and accepts either the compatible
  same-origin admin session or an owner/admin human access token.

### Service Identity

Status: Implemented

- Service tokens are issued/rotated under `/api/auth/service-token*`.
- Telemetry/services APIs enforce service-token claims where required.

### MQTT Principals

Status: Implemented

- Core tracks principal state and lifecycle for addon/system/generic identities.
- Principal actions and effective-access inspections are admin-controlled.

## Roles and Boundaries

Status: Implemented

- `owner`: full Core and ownership administration.
- `admin`: privileged control-plane and lifecycle writes.
- `member`: authenticated access only to explicitly permitted operations and
  personal resources.
- `service`: scoped service-to-core operations.
- `guest`: minimal explicitly permitted access.

Named permissions are resolved centrally. Owner changes require an owner;
members and guests cannot administer users or acquire an administrative cookie.

Installed PWA access additionally binds the human session to a Core-owned
enrolled device. Device, session, conversation, preference, and subscription
ownership are enforced independently of Tunnel reachability. The current live
acceptance status and physical-device matrix are recorded in
[Core Web App End-to-End Validation](./web-app-end-to-end-validation.md).

## Admin Session Configuration

Status: Implemented

Admin session behavior is configured by:

- `HEXE_ADMIN_TOKEN`
  Required for token-based admin auth and as the fallback signing basis for admin sessions.
- `HEXE_ADMIN_COOKIE_SECURE`
  Enables secure cookies when set to a truthy value.
- `HEXE_ADMIN_SESSION_TTL_SECONDS`
  Bounded to `300..604800` seconds in code.
- `HEXE_ADMIN_SESSION_SECRET`
  Optional explicit signing secret for admin session cookies.

Compatibility:

- `SYNTHIA_*` environment variables are read as legacy aliases when the matching `HEXE_*` variable is not set. New configuration should use `HEXE_*`.
- Existing `synthia_admin_session` cookies are accepted for the same signed admin-session payload, but new logins issue `hexe_admin_session`.

Implemented admin session routes:

- `POST /api/admin/session/login`
- `POST /api/admin/session/login-user`
- `GET /api/admin/session/status`
- `POST /api/admin/session/logout`

Admin reload control also uses the same admin token or session gate:

- `POST /api/admin/reload`
- `GET /api/admin/reload/status`

## Service Principal Token Issuance

Status: Implemented

- `POST /api/auth/service-token` supports admin-issued tokens and constrained service-principal issuance.
- Service-principal issuance uses:
  - `X-Service-Principal-Id`
  - `X-Service-Principal-Secret`
- The principal registry is loaded from `HEXE_SERVICE_PRINCIPALS_JSON`.

Supported principal config fields:

- `id`
- `secret`
- `subject` (optional)
- `allowed_audiences`
- `allowed_scopes`
- `max_ttl_s` (optional)

Enforcement in code:

- subject mismatch returns `service_principal_subject_mismatch`
- audience mismatch returns `service_principal_audience_forbidden`
- scope mismatch returns `service_principal_scope_forbidden`
- TTL above `max_ttl_s` returns `service_principal_ttl_exceeds_max`

## Generic Users vs System Principals

Status: Implemented

- Generic users can be lifecycle-managed and scoped to approved topic access.
- System/addon principals carry platform-owned responsibilities and reserved-family access as needed.

## MQTT Identity Model

Status: Partially implemented

- Effective-access model compiles principal permissions into deterministic ACL outputs.
- Generic users are blocked from reserved platform families.
- Future identity federation and advanced role policy inheritance are planned.

## Archived Legacy Behavior

Status: Implemented

- Earlier split identity guidance from `auth-and-users.md` and MQTT authority design notes has been consolidated here.

## Multi-User Human Sessions

Status: Implemented for Tasks 1005-1006

Human clients use these routes:

- `POST /api/auth/user/login`
- `POST /api/auth/user/device-login/challenge`
- `POST /api/auth/user/device-login/complete`
- `POST /api/auth/user/refresh`
- `POST /api/auth/user/logout`
- `GET /api/auth/user/sessions`
- `DELETE /api/auth/user/sessions/{session_id}`

Access tokens are short-lived, signed, and bound to the issuing Core, stable
user id, role, credential revision, and session id. Refresh credentials are
stored only as SHA-256 verifiers, rotate on use, and revoke the affected session
when reuse is detected. User disablement, deletion, role/password changes, and
session revocation are checked against persisted state for every access token.

An enrolled web-app installation relogs in through a two-step device-login
challenge without sending the account password. The challenge is short-lived,
single-use, and bound to the user, Core, device, RP ID, and canonical HTTPS
origin. Core issues the new device-bound session only after verifying both the
installation's Ed25519 signature and a WebAuthn assertion with required user
verification. Existing installations created before Task 1018 perform a
one-time password-authenticated passkey upgrade that also requires their
installation key. Normal logout revokes only the current session and does not
revoke enrollment or the passkey.

The compatible `hexe_admin_session` cookie remains same-origin and is not a
remote-app credential.

## Installed Web-App Enrollment

Status: Implemented

- `GET /api/auth/web-app/discovery` returns only the enrollment contract,
  stable Core id, canonical public hostname, and availability flag.
- `POST /api/auth/device-enrollments` creates a short-lived enrollment and
  returns its one-time proof only to the authorized owner/admin caller.
- `POST /api/auth/device-enrollments/{enrollment_id}/approve` explicitly
  approves the target user and device enrollment.
- `GET /api/auth/device-enrollments/{enrollment_id}` returns sanitized state.
- `POST /api/auth/device-enrollments/{enrollment_id}/passkey-options` returns
  proof-gated, short-lived platform-passkey registration options after approval.
- `POST /api/auth/device-enrollments/{enrollment_id}/complete` verifies the
  one-time proof, Ed25519 device-key possession, and origin/RP-bound WebAuthn
  registration with required platform user verification before binding the
  device and issuing a device-bound human session.
- `POST /api/auth/device-enrollments/{enrollment_id}/cancel` cancels an active
  enrollment.
- `POST /api/auth/devices/{device_id}/rotate-key` requires a device-bound
  access token plus signatures from both the old and replacement keys.

Core stores enrollment proofs and refresh credentials only as SHA-256
verifiers. Enrollment completion is single-use; expired, cancelled, wrong-Core,
wrong-proof, wrong-key, duplicate-device, and replay attempts fail closed.
Recovery uses a fresh owner/admin-approved enrollment with
`replace_device_id`, preserving the original approval and key-possession
boundary.

## See Also

- [MQTT Platform](../../mqtt/mqtt-platform.md)
- [Core Platform](./core-platform.md)
- [API Reference](./api-reference.md)
- [Telemetry And Usage](./telemetry-and-usage.md)
- [Data and State](./data-and-state.md)
- [Core Multi-User Remote Web App Security and Identity Contract](./multi-user-remote-web-app-security-contract.md)
