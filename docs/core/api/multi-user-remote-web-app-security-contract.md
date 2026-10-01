# Core Multi-User Remote Web App Security and Identity Contract

Status: Tasks 1005-1006 implemented; Task 1007 in progress; Tasks 1008-1014 remain planned

## Purpose

This contract defines the Core-owned identity, authorization, session, device,
and notification boundaries for multiple human users accessing one Core through
the managed Hexe web app and Cloudflare Tunnel. Tasks 1005-1012 implement and
validate this contract. The user, role, human-token, refresh-rotation, session,
and revocation behavior in Task 1005 plus device enrollment and key possession
in Task 1006 are available; remote route allow-listing and notification
behavior remain unavailable.

The public hostname is addressability only. Knowing a Core id or reaching
`<core-id>.hexe-ai.com` never authorizes a request.

## Implemented Task 1005 Baseline

The current implementation has:

- a migrated SQLite `users` table with stable opaque `user_id` values
- roles `owner`, `admin`, `member`, and `guest`
- PBKDF2-SHA256 password verifiers
- human login and rotating refresh APIs under `/api/auth/user/*`
- individually listable and revocable persisted human sessions
- an HttpOnly signed `hexe_admin_session` cookie with a bounded lifetime
- admin user list, upsert, and delete routes under `/api/admin/users`
- protection against deleting or disabling the last enabled administrator
- append-only, secret-redacted Core audit records
- a managed Cloudflare Tunnel whose Core API, node proxy, and addon proxy paths
  terminate at Core

Compatibility admin cookies are not persisted as independently revocable human
sessions and remain same-origin only. Installed-device identity, one-time
owner-approved enrollment, Ed25519 possession proof, recovery enrollment, and
dual-proof key rotation are implemented. Remote route allow-listing and
push-subscription ownership are not yet implemented.

## Identity Model

### Core

`core_id` is the stable audience and ownership boundary for every human access
credential. A credential issued by one Core is invalid at every other Core.
The public hostname and tunnel id are routing metadata, not authenticators.

### Human user

Each human has a stable, opaque `user_id`. Username is a mutable, unique login
name and display attribute; it is not the durable authorization or audit key.
A user belongs to exactly one Core in this contract. Cross-Core identity
federation is outside the initial scope.

Required persisted user fields:

- `user_id`
- `core_id`
- `username` and normalized uniqueness key
- password verifier and verifier metadata
- `role`
- `enabled`
- `created_at`, `updated_at`, and optional `disabled_at`
- credential revision used to invalidate sessions after password or security
  changes

Password verifiers, refresh-token verifiers, device private keys, and gateway
credentials are never returned by user APIs.

### Installed web-app device

An installed browser/PWA instance is a device identity distinct from a user and
from a session. A device belongs to one Core and one user and has a stable
`device_id`, public key, display name, lifecycle state, and last-seen metadata.
The private key remains on the device. Reinstalling without recovery creates a
new device identity.

### Session

A session binds one `session_id` to `core_id`, `user_id`, and, for installed
clients, `device_id`. Sessions are individually listable and revocable. Session
state includes creation, last use, expiry, revocation, credential revision, and
bounded client metadata. Raw access and refresh credentials are never stored.

### Push subscription

A push subscription belongs to one Core, user, and device. Core stores a
bounded gateway reference and notification preferences; the gateway stores the
provider-specific delivery material. Neither side may retarget the subscription
to another Core, user, or device.

### Notification gateway principal

The central gateway is a service principal with a narrow audience and scopes
for subscription registration/cleanup and Core-approved delivery only. It is
not a Core administrator and cannot read arbitrary Core state or choose users.

## Human Roles

Roles are ordered by permissions, not by token format:

| Role | Intended authority |
| --- | --- |
| `owner` | Full Core administration, ownership transfer, user/role management, high-impact credential and remote-access controls. |
| `admin` | Day-to-day Core, node, addon, and user administration except owner-only ownership and root-security operations. |
| `member` | Authenticated household/member access to explicitly allowed operational features and personal resources. |
| `guest` | Minimal, explicitly granted and time-bounded or policy-bounded access; no implicit read access to private Core state. |

Permissions are checked centrally by named capability. Role comparison alone
must not be scattered through route handlers. Deny is the default. At minimum:

- ownership transfer, deletion of the last owner, gateway credential rotation,
  and global remote-access revocation require `owner`
- user creation, supported role changes below owner, user enable/disable,
  device administration, and session administration require `owner` or an
  explicitly permitted `admin`
- node management, Supervisor updates, tunnel configuration, provider secrets,
  and credential operations remain privileged owner/admin operations
- members and guests can access only allow-listed routes and records authorized
  for their own identity
- users may inspect and revoke their own sessions/devices and manage their own
  preferences unless policy says otherwise

At least one enabled owner must exist. Disabling, deleting, or demoting the last
enabled owner fails closed.

## Existing User Migration

Migration is in place and transactional before the new role rules are enabled.
It preserves existing usernames, password hashes, creation timestamps, enabled
state, and audit continuity. It adds a stable `user_id` and never creates a
duplicate solely to assign a new role.

Migration rules:

1. The operator supplies or confirms one existing enabled administrator as the
   initial owner.
2. That exact record is promoted from `admin` to `owner` without changing its
   password verifier.
3. Other enabled administrators remain `admin` unless explicitly promoted.
4. Existing `guest` records remain `guest`.
5. Migration refuses to enable multi-role enforcement if the selected record
   is absent, disabled, or not currently an administrator.
6. Migration is idempotent and records a redacted audit event containing the
   migrated `user_id`, old role, new role, and migration version.
7. Rollback may restore code compatibility, but must never silently demote the
   only owner or discard newly created identities, sessions, or devices.

For this Core, the confirmed initial-owner migration target is the existing
`Dan` account. Task 1005 must preserve that record and promote it to `owner`.
The existing seeded `admin` account remains an enabled `admin` unless the owner
changes or disables it after migration.

## Authentication and Credential Contract

### Local compatibility login

The existing same-origin Core WebUI cookie flow remains available during the
migration. Owner and admin users may use it for privileged local administration.
The compatibility cookie must not become a cross-origin installed-app
credential and must eventually map to a persisted, revocable session identity.

The configured `X-Admin-Token` remains an automation/bootstrap compatibility
credential. It is never shared with human remote clients, embedded in links, or
stored by the central web app.

### Remote installed-app login

Remote clients use short-lived access tokens and rotated refresh credentials.
An access token contains at least:

- issuer identifying the Core
- audience bound to that same Core and the remote web-app API
- subject equal to stable `user_id`
- `session_id`
- optional `device_id` where device enrollment is required
- current role or a bounded permission/version reference
- credential revision
- issued-at, not-before, expiry, and unique token id

Access tokens are bearer credentials with a short lifetime. Refresh credentials
are high-entropy, session- and device-bound, stored by Core only as non-recoverable
verifiers, rotated on every successful use, and protected by reuse detection.
Reuse revokes the affected session or token family and emits a redacted audit
event. Credentials are never placed in URL query strings or fragments.

## Enrollment and Device Binding

Device enrollment starts from an authenticated Core owner/admin action allowed
by policy. Core creates a short-lived, single-use enrollment session. A QR or
deep link contains only the Core hostname, enrollment id, contract version,
expiry, and a high-entropy one-time proof.

The installed app generates a device key pair and proves possession of the
private key. Approval binds Core, user, device id, device public key, enrollment
session, and issued refresh credential. Expired, cancelled, consumed, replayed,
wrong-Core, or wrong-key enrollment attempts fail closed.

Email address, Google identity, tunnel reachability, or possession of the Core
hostname alone never attaches a device to a user.

## Authorization Boundary

Remote access is limited to an explicit route allow-list. Every protected route
checks Core audience, user enabled state, session state, credential revision,
role/permission, resource ownership, and device state when required.

Before authentication, the canonical public host exposes only the web-app
bootstrap/realtime APIs, human login/session APIs, device enrollment APIs, safe
web-app discovery, and user-based admin-session login/status/logout. Other API
paths return `404`. A valid admin session cookie retains the broader API surface
needed by `/admin`; `X-Admin-Token` is rejected on the public host and remains a
local automation compatibility mechanism only.
Public user login, refresh, admin-user login, and enrollment completion share a
source-aware limit of 10 attempts per minute. Overflow returns `429` with
`Retry-After`; local/LAN authentication compatibility is unchanged.

Task 1007 currently exposes `GET /api/web-app/bootstrap` as the first protected
web-app route. It requires a valid human access token whose session is bound to
an active enrolled device owned by the same user and Core. Its response contains
safe Core identity, current user permissions, session and device identifiers,
and conservative feature/notification availability. It does not return device
public keys, credentials, enrollment proofs, or administrative secrets.

The same enrolled identity can connect to `/api/web-app/realtime` with a WebSocket
`Authorization` header. The handshake rejects non-public hosts, disallowed
origins, anonymous sessions, and credentials in query strings. Connections are
revalidated on each client message and heartbeat, accept bounded in-band
`auth.renew` messages only for the same user/device identity, and close after
session expiry or device revocation. Client messages are limited to 16 KiB.

Node and addon proxy requests retain their existing target-trust and management
authorization checks in addition to human authorization. A remote user token
cannot bypass Core-to-node management authorization or cause Core to forward a
caller-supplied management credential.

Changes to password, role, enabled state, user existence, session state, or
device state invalidate affected access within the access-token lifetime and
immediately at refresh. High-impact changes increment credential revision or
revoke the relevant sessions so stale credentials cannot remain usable.

## Browser and Network Security

- Production CORS allows only the exact approved Hexe app origin(s); development
  origins are explicit and development-only.
- Credentialed wildcard origins are forbidden.
- Local cookie mutations retain same-origin `Origin`/`Referer` CSRF checks.
- Remote clients use `Authorization` headers, not cross-origin Core cookies.
- WebSocket or SSE connections authenticate during a protected handshake and
  have a defined renewal/reconnect behavior; credentials do not appear in URLs.
- Login, refresh, enrollment, recovery, and notification endpoints have
  identity-aware and source-aware rate limits.
- TLS is required for public remote access. Direct LAN HTTP remains a local
  compatibility surface and cannot weaken public credential requirements.

For the implemented `/api/web-app/*` boundary, the production browser origin is
exactly `https://<core-id>.<platform-domain>`. Preflight permits only the
implemented `GET`/`HEAD` methods and the `Authorization` and `Content-Type`
headers. Development origins are enabled only by `HEXE_ENABLE_DEV_CORS`; a
disallowed public origin fails with `cors_origin_not_allowed`. Requests without
an `Origin` header remain available to authenticated installed/native clients.
The same public boundary rejects credentials in query strings, rejects declared
request bodies larger than 1 MiB, and applies a source-aware default limit of
120 non-preflight requests per minute with `429` and `Retry-After` on overflow.
These transport limits do not alter the local Core UI path.

## Session and Revocation Semantics

Core supports listing and revoking one session, all sessions for one device,
all sessions for one user, and all remote sessions for the Core. Revocation of
one identity does not affect unrelated users unless an owner explicitly selects
a Core-wide operation.

- logout revokes the current session and deletes client credentials
- user disable/delete revokes all user sessions and devices according to
  retention policy
- password change revokes other sessions by default and rotates credential
  revision
- role change invalidates prior authorization immediately or within the stated
  bounded access-token window
- device loss revokes that device and its sessions/subscriptions only
- Core removal or ownership reset revokes all remote credentials and gateway
  bindings

## Notification Privacy Boundary

Core selects recipients using authorization, ownership, notification category,
severity, device preferences, and quiet hours. The gateway receives only a
bounded safe title/body, Core-relative deep link, idempotency key, expiry, and
opaque subscription reference required for delivery.

Notification payloads never include admin/session tokens, refresh credentials,
provider credentials, tunnel credentials, raw email bodies, attachments, voice
audio, or unrestricted event payloads. Protected detail is fetched from Core
after the user opens the app and authenticates.

Disabling a user, revoking a device, or deleting a subscription prevents future
delivery to that target without affecting unrelated users or devices.

## Audit Requirements

Core records redacted events for:

- login success and failure
- access/refresh issuance and refresh-token reuse detection
- logout and session revocation
- user creation, deletion, enable/disable, role change, and password change
- owner selection and ownership transfer
- enrollment creation, approval, rejection, expiry, cancellation, and replay
- device and push-subscription creation, update, and revocation
- authorization denial for privileged or cross-user access
- notification recipient-policy decisions and gateway delivery outcomes

Audit identity uses stable `user_id`, plus session/device ids when relevant.
Passwords, password hashes, raw tokens, one-time proofs, cookies, private keys,
push endpoints, and provider credentials are never logged.

## Threat Model and Required Defenses

| Threat | Required defense |
| --- | --- |
| Guessed Core hostname or id | Authentication and Core-audience validation on every protected route. |
| Stolen enrollment link | Short expiry, single use, explicit approval, high-entropy proof, and device-key possession. |
| Stolen refresh credential | Non-recoverable server verifier, rotation, reuse detection, session/device binding, and revocation. |
| Malicious website | Exact-origin CORS, no wildcard credentials, CSRF checks for cookies, and no credentials in URLs. |
| Replayed API or gateway request | Expiry, nonce/token id, body integrity where applicable, idempotency, and replay cache. |
| Compromised push endpoint | Opaque Core-bound reference, bounded payload, per-device revocation, and no protected detail in pushes. |
| Cross-user data access | Stable user ownership checks and deny-by-default route/resource permissions. |
| Removed or disabled user | Session/device revocation, credential revision, refresh denial, and bounded access-token lifetime. |
| Compromised central app/gateway | No Core admin token, least-privilege service principal, Core audience binding, and narrow APIs. |

## Ownership by Component

- Core owns users, roles, permissions, credentials, sessions, device records,
  enrollment approval, notification policy, audit, and revocation.
- Supervisor owns the local `cloudflared` process and reports runtime state; it
  does not authenticate human users.
- Cloudflare Tunnel transports requests and does not grant application access.
- The installed web app stores its device private key and refresh credential
  using platform-appropriate protected storage and presents Core-issued proof.
- The central gateway stores provider delivery material and performs only
  Core-authorized, Core-bound delivery.
- Nodes/addons continue to own their resource-level validation behind Core's
  authenticated proxy and management-authorization boundaries.

## Implementation Sequence

1. Task 1005 implements users, roles, permissions, sessions, credentials, and
   the `Dan` owner migration.
2. Task 1006 implements enrollment and device credentials.
3. Task 1007 implements the allow-listed remote API and realtime boundary.
4. Tasks 1008-1010 implement device/subscription state, notification policy,
   and gateway publishing.
5. Task 1011 implements owner/user administration UX.
6. Task 1012 validates two-user isolation and end-to-end revocation/delivery.

No Task 1005+ endpoint, schema, or UI behavior should be advertised as
implemented until its code and focused verification are complete.

## See Also

- [Auth and Identity](./auth-and-identity.md)
- [Node-Management Authorization](../node-management-authorization.md)
- [Edge Gateway](./edge-gateway.md)
- [Frontend and UI](../frontend/frontend-and-ui.md)
- [Data and State](./data-and-state.md)
- [MQTT Platform](../../mqtt/mqtt-platform.md)
