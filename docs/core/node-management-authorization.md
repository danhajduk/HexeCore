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

Trusted-node management introspection is limited per node and source address
to 1,200 requests per rolling minute. This accommodates concurrent management
UI initialization and polling while retaining abuse protection.

Core rechecks authorization revocation, token expiry, current operator role and
enabled state, exact target binding, current target trust, and permissions.
Core retains rotated verification keys through token lifetime. It audits
issuance, successful validation, and revocation without recording tokens or
signing secrets.

For the supported browser flow, the Core WebUI never receives the token. The
operator opens `/nodes/proxy/ui/<node-id>/...`; Core validates the HttpOnly admin
session and current target trust, issues and caches a five-minute authorization
containing all seven permissions, strips any caller-supplied management header,
and injects its own `X-Hexe-Management-Authorization` into UI, API, binary asset,
download, and WebSocket proxy requests. The node remains responsible for Core
introspection and route authorization.

Cookie-authenticated unsafe Core requests require a same-origin `Origin` or
`Referer`. Explicit token clients use `claims.exp`; there is no refresh endpoint.
Direct node management UI access and legacy `VITE_ADMIN_TOKEN` /
`X-Hexe-Admin-Token` bypasses are not supported. Operators use the Core-mounted
URL so browser-native resources such as images receive proxy authorization.

Onboarding and retrust are Core-owned proof and approval workflows. Core does
not issue a management token to an untrusted or unsupported target. A node may
leave health, OpenAPI/schema, and non-sensitive static discovery routes public;
those routes must not mutate state or disclose credentials.

The complete live consumer contract is published at
`GET /api/schemas/client-core/v1/node-management-authorization-contract.md`.
