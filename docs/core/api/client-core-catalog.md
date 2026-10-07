# Client Core V1 Catalog

Status: Implemented

Core publishes a client-oriented discovery catalog for trusted node developers:

- `GET /api/schemas/client-core/v1`
- `GET /api/schemas/client-core/v1/schema-catalog.v1.response.schema.json`
- `GET /api/schemas/client-core/v1/assistant-actor-assertion-claims.v1.schema.json`
- `GET /api/schemas/client-core/v1/assistant-approval-assertion-claims.v1.schema.json`
- `GET /.well-known/hexe-core-jwks.json`
- `GET /api/schemas/client-core/v1/README.md`

The catalog identifies the current onboarding, capability, governance, budget,
service-resolution, authorization, telemetry, hardware-access, and MQTT event
contract APIs. Every listed API and catalog entry carries an implementation
status so clients can distinguish available behavior from planned contracts.

## Service-token security

The catalog also publishes:

- `GET /api/schemas/client-core/v1/service-token-security-contract.md`
- `GET /api/schemas/client-core/v1/node-management-authorization-contract.md`

The Assistant assertion schemas define Core-owned, short-lived claim shapes
for `assistant.v1`. Actor assertions are bound to an exact requester node,
Assistant Engine audience, Core, conversation, and turn. Approval assertions
add an exact action, intent revision, canonical argument hash, target
capability, and single-use approval correlation. Neither schema permits
transcripts, raw audio, biometric material, or general profile data.

The JWKS endpoint publishes only active or still-valid retired Ed25519 public
verification keys. Assistant signing keys remain in Core's sensitive settings
boundary, and retired public keys remain discoverable only through the latest
assertion expiry plus the 30-second clock-skew window.

Trusted Assistant providers use
`POST /api/system/nodes/assistant/assertions/introspect` before consequential
execution and approval resumption. Core authenticates the provider node,
requires it to own the exact service audience, rechecks the assertion binding
and current authorization epochs, and atomically consumes approval assertions
when requested. Invalid assertions return stable inactive error codes; foreign
audiences and untrusted providers fail with authorization errors.

Trusted channel nodes request an actor assertion through
`POST /api/system/nodes/assistant/actor-assertions`. Core requires the caller's
node ID to match the request, an active exact-audience service-access grant,
and a trusted Interaction provider audience. Person evidence must resolve to
an active Core-owned person and household; endpoint context must match Core's
room assignment. Node-originated assertions never acquire a `user_id`.
Claimed verified speaker identity is downgraded to probable unless evidence is
present and confidence is at least 0.90. Unknown, probable, and conflicted
actors receive submit authority only.

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
