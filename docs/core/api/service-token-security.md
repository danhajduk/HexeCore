# Core Service-Token Security

Status: Implemented

Core owns service-token signing, governed authorization, key rotation, and
provider-facing introspection. Signing secrets remain private to Core.

## Governed execution tokens

`POST /api/system/nodes/services/authorize` authenticates the caller with its
node ID and `X-Node-Trust-Token`, resolves the requested task family through
governance and budget policy, and issues a short-lived execution token.

Execution tokens contain:

- `iss=hexe-core`
- `token_use=node_service`
- a unique `authorization_id`
- `sub`: authenticated calling node ID
- `aud`: exact authorized logical provider service
- `scp`: resolved `service.execute:<task_family>` permissions
- integer `iat` and `exp`
- unique `jti`

Provider catalog declarations can narrow execution requirements but do not
create privileged service-access grants.

## Privileged service-access grants

Management and discovery access is separate from task execution. Administrators
manage persistent, audited grants through:

- `GET|POST /api/system/nodes/service-access/grants`
- `GET|PUT /api/system/nodes/service-access/grants/{grant_id}`
- `POST /api/system/nodes/service-access/grants/{grant_id}/revoke`

A grant binds a caller node, target logical service, allowed scopes, lifecycle
status, and optional expiration. No grants are created automatically.

Trusted callers exchange an active grant for a 600-second token through:

`POST /api/system/nodes/service-access/authorize`

```json
{
  "node_id": "node-caller",
  "service_id": "node-service:node-ai-provider:openai",
  "requested_scopes": ["ai.prompts.read"]
}
```

The request requires `X-Node-Trust-Token`. Core issues only the requested
subset authorized by an active matching grant. The resulting token uses
`token_use=node_service_access` and its `authorization_id` is the grant ID.

Supported privileged scopes are:

- `ai.prompts.read`, `ai.prompts.write`, `ai.prompts.lifecycle`, `ai.prompts.review`
- `ai.image_templates.read`, `ai.image_templates.write`
- `ai.image_templates.lifecycle`, `ai.image_templates.review`
- `ai.jobs.read`, `ai.jobs.cancel`
- `ai.artifacts.read`, `ai.artifacts.ack`
- `ai.services.read`

The service node owns its operation-to-required-scope mapping. Requiring a
scope does not grant it; Core grants and issues the authorization.

## Provider token introspection

`POST /api/system/nodes/services/introspect`

Provider authentication requires both headers:

```http
X-Node-Id: node-ai-provider
X-Node-Trust-Token: <provider trust token>
```

Request:

```json
{
  "token": "<Core-issued service token>",
  "expected_audience": "node-service:node-ai-provider:openai",
  "required_scopes": ["ai.prompts.read"]
}
```

`expected_audience` is optional but recommended. `required_scopes` may be empty;
when supplied, every scope must be present.

Active response, HTTP 200:

```json
{
  "active": true,
  "claims": {
    "sub": "node-caller",
    "aud": "node-service:node-ai-provider:openai",
    "scp": ["ai.prompts.read"],
    "exp": 1790472000,
    "iat": 1790471400,
    "jti": "access-token-id",
    "iss": "hexe-core",
    "token_use": "node_service_access",
    "authorization_id": "sag-grant-id"
  },
  "error_code": null
}
```

Inactive response, HTTP 200:

```json
{
  "active": false,
  "claims": null,
  "error_code": "token_expired"
}
```

Stable inactive codes:

- `token_malformed`
- `token_signature_invalid`
- `token_expired`
- `token_claims_invalid`
- `token_use_invalid`
- `token_audience_mismatch`
- `token_scope_insufficient`
- `token_subject_untrusted`
- `token_authorization_revoked`

Provider-authentication and availability failures use:

- `401 node_identity_required`
- `401 node_trust_token_required`
- `403 untrusted_node`
- `403 service_token_audience_not_owned`
- `429 rate_limited`
- `503 token_validation_unavailable`

Providers must fail closed unless the result is HTTP 200 with `active=true`.
Core never logs or returns the submitted bearer token or signing material.

## Identity and operation binding

The service node owns request binding after successful introspection:

- request `requested_by` must equal verified `claims.sub`
- request `service_id` must equal verified `claims.aud`
- the operation's service-owned required scopes must be present in `claims.scp`

Caller-supplied identity and service fields never create authorization.

## Rotation

The active key signs new tokens. On rotation, the old key becomes
verification-only. Core records the latest token expiration signed by each key
and retains that key until the expiration plus 30 seconds of clock skew. Rapid
rotations therefore do not invalidate otherwise-live tokens.

## Provider adoption

Core introspection and authorization are implemented. Universal provider-side
enforcement remains partially implemented until every resolved provider adopts
this contract at its execution and management endpoints.
