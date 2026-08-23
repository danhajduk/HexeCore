# Core Communication API Guide

Status: Implemented

This guide summarizes node-facing Core communication APIs and JSON contracts that are not plain admin UI operations.

## Node Bridge MQTT Grants

Bridge grants let a trusted node request MQTT topics for an embedded bridge and then claim the provisioned bridge credential after admin approval.

### Request Topics

```http
POST /api/system/mqtt/node-bridge-grants/request
X-Node-Id: node-6812313e6d1efad6
X-Node-Trust-Token: <node trust token>
Content-Type: application/json
```

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

### Admin Approval

```http
POST /api/system/mqtt/node-bridge-grants/{grant_id}/approve
X-Admin-Token: <admin token>
```

Admin approval does not deliver credentials to the node. It only approves the topic set.

### Claim Credential

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

Response:

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

The `mqtt.password` field is only returned by the credential claim endpoint. Grant list/detail APIs and admin approval APIs do not expose passwords.

### Claim Errors

Common claim errors:

```text
node_bridge_grant_not_found
node_bridge_grant_node_mismatch
node_bridge_grant_bridge_mismatch
node_bridge_grant_not_approved:<status>
node_bridge_grant_rejected
node_bridge_grant_revoked
credential_store_unavailable
mqtt_setup_not_ready
credential_not_retrievable_rotate_required
```

## JSON Schemas

Related generated schema docs:

- [mqtt.integration.models.schema.json](../../json_schema/mqtt.integration.models.schema.json)
- [mqtt.router.request-models.schema.json](../../json_schema/mqtt.router.request-models.schema.json)
- [mqtt_integration_state.store.schema.json](../../json_schema/mqtt_integration_state.store.schema.json)
