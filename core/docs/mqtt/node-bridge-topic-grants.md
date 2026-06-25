# Node Bridge MQTT Topic Grants

Status: Implemented

Node bridge grants let a trusted node request scoped MQTT access for an external bridge that runs inside the node, such as a Home Assistant bridge. The flow separates topic approval from credential delivery:

```text
node requests grant -> admin approves -> node claims credential -> node uses bridge MQTT creds
```

## Request Grant

Trusted node endpoint:

```http
POST /api/system/mqtt/node-bridge-grants/request
X-Node-Id: node-6812313e6d1efad6
X-Node-Trust-Token: <node trust token>
Content-Type: application/json
```

Request body:

```json
{
  "node_id": "node-6812313e6d1efad6",
  "bridge_id": "homeassistant",
  "bridge_type": "homeassistant",
  "publish_topics": [
    "homeassistant/+/hexe_ecosystem/+/config",
    "homeassistant/hexe_ecosystem/state"
  ],
  "subscribe_topics": [
    "homeassistant/status"
  ]
}
```

Core validates node trust and stores the request as `requested`. The node cannot approve topics, change approved topics, or claim another node's grant.

## Admin Approval

Admin endpoint:

```http
POST /api/system/mqtt/node-bridge-grants/{grant_id}/approve
X-Admin-Token: <admin token>
```

Approval copies requested topics into the approved topic lists. Admin list and detail endpoints expose safe grant metadata only:

```http
GET /api/system/mqtt/node-bridge-grants
GET /api/system/mqtt/node-bridge-grants/{grant_id}
```

These endpoints never return MQTT passwords.

## Credential Claim

After approval, the owning trusted node claims the MQTT credential:

```http
POST /api/system/mqtt/node-bridge-grants/{grant_id}/credential/claim
X-Node-Id: node-6812313e6d1efad6
X-Node-Trust-Token: <node trust token>
Content-Type: application/json
```

Optional body:

```json
{
  "bridge_id": "homeassistant"
}
```

Successful response:

```json
{
  "ok": true,
  "grant": {
    "grant_id": "node-6812313e6d1efad6:homeassistant",
    "node_id": "node-6812313e6d1efad6",
    "bridge_id": "homeassistant",
    "bridge_type": "homeassistant",
    "status": "active",
    "delivery_status": "delivered",
    "credential_claimed_by_node_id": "node-6812313e6d1efad6"
  },
  "mqtt": {
    "username": "hb_6812313e6d1efad6_homeassistant",
    "password": "<mqtt password>"
  }
}
```

Claim authorization rules:

- `X-Node-Id` must authenticate with `X-Node-Trust-Token`.
- `grant.node_id` must match `X-Node-Id`.
- Optional `bridge_id` must match `grant.bridge_id`.
- `grant.status` must be `approved`, `active`, or `provisioned`.
- `rejected` and `revoked` grants cannot be claimed.

Core creates or reuses the managed `node_bridge` MQTT principal, reconciles MQTT ACLs, and returns the credential only from the claim endpoint.

## Delivery Metadata

Core stores safe delivery metadata on the grant:

```text
credential_claimed_at
credential_claimed_by_node_id
last_credential_delivery_at
delivery_status
```

Raw MQTT passwords are not stored on the grant. They are retrieved from the MQTT credential store when available.

## Re-Claim Policy

Core supports re-claim when it can retrieve the credential from the MQTT credential store. If a previously delivered credential is no longer retrievable, Core returns:

```text
credential_not_retrievable_rotate_required
```

Rotation remains an admin-controlled path. A future node rotation request endpoint may allow nodes to request rotation without self-approving credentials.

## Audit Events

Core emits audit events without passwords:

```text
node_bridge_credential_claim_requested
node_bridge_credential_claim_succeeded
node_bridge_credential_claim_denied
node_bridge_credential_rotated
node_bridge_credential_revoked
```
