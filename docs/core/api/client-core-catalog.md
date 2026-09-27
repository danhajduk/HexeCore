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

## Proposed service-token security

The catalog also publishes:

- `GET /api/schemas/client-core/v1/service-token-introspection-proposal.md`

The document and its corresponding `security_proposals` catalog entries are
marked `Not implemented`. Publication is design discovery only and does not
register `POST /api/system/nodes/services/introspect`.

The proposal covers provider authentication, audience ownership, service-token
claim verification, stable inactive responses, rate limiting, governed
privileged-scope issuance, request identity binding, and lifetime-based signing
key retention. Core signing secrets remain private to Core.
