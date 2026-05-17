# Node JSON Schemas

Status: Implemented

This folder is the node-local schema catalog for implementers working on onboarding, trust, runtime status, governance, notification, and Core-rendered UI contracts.

Most files here mirror the broader repository schema catalog in `docs/json_schema/` so node-focused work has a single nearby reference point. `full-onboarding-metadata.schema.json` is the node metadata refresh payload used by:

```http
PUT /api/system/nodes/registrations/{node_id}/metadata
```

Core-owned fields such as identity, trust status, MQTT credentials, governance state, and budget state are intentionally excluded from the metadata refresh schema.

## Schema Groups

- Onboarding and registration: `node_onboarding_start_request.schema.json`, `node_onboarding_sessions.store.schema.json`, `node_registrations.store.schema.json`, `full-onboarding-metadata.schema.json`
- Trust and lifecycle: `node_trust_records.store.schema.json`, `node_lifecycle_topic_payload.schema.json`, `node_status_topic_payload.schema.json`
- Capabilities and governance: `node_capability_declaration_manifest.schema.json`, `node_capability_declaration_response.schema.json`, `node_capability_profiles.store.schema.json`, `node_governance_bundles.store.schema.json`, `node_governance_status.store.schema.json`
- Runtime and registry views: `nodes.models.schema.json`, `nodes.models-resolution.schema.json`, `supervisor.runtime-nodes.schema.json`
- Node UI: `node_ui_manifest.schema.json`, `node_ui_card_responses.schema.json`
- Messaging and events: `node_notification_request.schema.json`, `node_notification_result.schema.json`, `node_originated_domain_event.schema.json`, `core_promoted_node_domain_event.schema.json`, `node_telemetry_events.store.schema.json`
- Budgets: `node_budgets.store.schema.json`
