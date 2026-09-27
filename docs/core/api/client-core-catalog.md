# Client Core V1 Catalog

Status: Implemented

Core publishes a client-oriented discovery catalog for trusted node developers:

- `GET /api/schemas/client-core/v1`
- `GET /api/schemas/client-core/v1/schema-catalog.v1.response.schema.json`
- `GET /api/schemas/client-core/v1/README.md`

The catalog identifies the current onboarding, capability, governance, budget,
service-resolution, authorization, telemetry, hardware-access, and MQTT event
contract APIs. Every listed API and catalog entry carries an implementation
status so clients can distinguish available behavior from planned contracts.

## Service-token security

The catalog also publishes:

- `GET /api/schemas/client-core/v1/service-token-security-contract.md`
- `GET /api/schemas/client-core/v1/node-management-authorization-contract.md`

Provider introspection, governed privileged-scope issuance, and lifetime-based
rotation retention are implemented. Universal provider enforcement is marked
`Partially implemented` because each service node must adopt the contract.

The proposal covers provider authentication, audience ownership, service-token
claim verification, stable inactive responses, rate limiting, governed
privileged-scope issuance, request identity binding, and lifetime-based signing
key retention. Core signing secrets remain private to Core. See
[Core Service-Token Security](./service-token-security.md).

## Node-management authorization

The node-management contract applies to every managed node and keeps operator
authority separate from workload execution tokens. It defines single-node
binding, category permissions, revocation, WebUI proxy propagation, trusted-node
introspection, recovery exceptions, audit behavior, and stable fail-closed
results. See [Node-management authorization](../node-management-authorization.md).
