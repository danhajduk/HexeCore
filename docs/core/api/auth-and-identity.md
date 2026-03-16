# Auth and Identity

## Identity Domains

### Admin Users

Status: Implemented

- Admin sessions support token and credential login flows.
- User CRUD is exposed under admin APIs.

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

- `admin`: privileged control-plane and lifecycle writes.
- `service`: scoped service-to-core operations.
- guest/read-only surfaces remain limited to non-privileged endpoints.

## Admin Session Configuration

Status: Implemented

Admin session behavior is configured by:

- `SYNTHIA_ADMIN_TOKEN`
  Required for token-based admin auth and as the fallback signing basis for admin sessions.
- `SYNTHIA_ADMIN_COOKIE_SECURE`
  Enables secure cookies when set to a truthy value.
- `SYNTHIA_ADMIN_SESSION_TTL_SECONDS`
  Bounded to `300..604800` seconds in code.
- `SYNTHIA_ADMIN_SESSION_SECRET`
  Optional explicit signing secret for admin session cookies.

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
- The principal registry is loaded from `SYNTHIA_SERVICE_PRINCIPALS_JSON`.

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

Status: Implemented (Phase 2 basis), Partial (future expansion)

- Effective-access model compiles principal permissions into deterministic ACL outputs.
- Generic users are blocked from reserved platform families.
- Future identity federation and advanced role policy inheritance are planned.

## Archived Legacy Behavior

Status: Archived Legacy

- Earlier split identity guidance from `auth-and-users.md` and MQTT authority design notes has been consolidated here.

## See Also

- [MQTT Platform](../mqtt/mqtt-platform.md)
- [Core Platform](./core-platform.md)
- [API Reference](./api-reference.md)
- [Telemetry And Usage](./telemetry-and-usage.md)
- [Data and State](./data-and-state.md)
