# Node-management authorization

Core uses a separate operator authorization boundary for management APIs on
every managed node. Workload service tokens (`node_service` and
`node_service_access`) cannot authorize node management.

An authenticated Core administrator requests a five-minute, single-node token
at `POST /api/system/nodes/management/authorize`. The token identifies the
operator in `sub`, binds the target as `aud=node-management:<node-id>`, uses
`token_use=node_management`, and carries only the requested permissions:

- `node.manage.read`
- `node.manage.configuration`
- `node.manage.operations`
- `node.manage.assets`
- `node.manage.credentials`
- `node.manage.lifecycle`
- `node.manage.diagnostics`

The target calls `POST /api/system/nodes/management/introspect` with its own
`X-Node-Id` and `X-Node-Trust-Token`. It permits the operation only for HTTP
200 with `active=true` and all route-required permissions. It must fail closed
if Core cannot validate the token.

Core rechecks authorization revocation, token expiry, current operator role and
enabled state, exact target binding, current target trust, and permissions.
Core retains rotated verification keys through token lifetime. It audits
issuance, successful validation, and revocation without recording tokens or
signing secrets.

The Core WebUI obtains authorization using its HttpOnly admin session and sends
the token as `X-Hexe-Management-Authorization` through the authenticated node
proxy. The proxy forwards that header; the node remains responsible for Core
introspection and route authorization.

Onboarding and retrust are Core-owned proof and approval workflows. Core does
not issue a management token to an untrusted or unsupported target. A node may
leave health, OpenAPI/schema, and non-sensitive static discovery routes public;
those routes must not mutate state or disclose credentials.

The complete live consumer contract is published at
`GET /api/schemas/client-core/v1/node-management-authorization-contract.md`.
