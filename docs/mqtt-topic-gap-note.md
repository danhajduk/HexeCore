# MQTT Topic Families Gap Note

Last Updated: 2026-03-09 06:57 US/Pacific

## Scope

Audit of currently implemented Synthia MQTT topic families versus embedded MQTT Phase 1 topic-contract needs.

## Already Implemented

From code:
- Subscriptions (`backend/app/system/mqtt/manager.py`):
  - `synthia/core/mqtt/info`
  - `synthia/addons/+/announce`
  - `synthia/addons/+/health`
  - `synthia/services/+/catalog`
  - `synthia/policy/grants/+`
  - `synthia/policy/revocations/+`
- Reserved platform checks (`backend/app/system/mqtt/topic_policy.py` / `authority_policy.py`):
  - `synthia/system/...`
  - `synthia/core/...`
  - `synthia/supervisor/...`
  - `synthia/scheduler/...`
  - `synthia/policy/...`
  - `synthia/telemetry/...`
- Bootstrap publish for embedded startup reconcile:
  - `synthia/bootstrap/core` retained QoS 1 (`backend/app/system/mqtt/startup_reconcile.py`)

## Documented But Inconsistent

- Docs list reserved addon scoping (`synthia/addons/<addon_id>/...`) but reserved-prefix enforcement currently focuses on platform families above.
- Topic ownership/retain/QoS defaults were previously distributed across multiple docs rather than one canonical tree spec.
- Bootstrap topic contract existed, but top-level reserved-family map was not centralized with implementation-status markers.

## Missing But Needed For Embedded MQTT Phase 1

Not developed in code yet:
- Explicit node topic family implementation (`synthia/nodes/<node_id>/...`).
- Additional Core operational subtrees (`synthia/core/status/...`, `synthia/core/health/...`, `synthia/core/events/...`) beyond `synthia/core/mqtt/info`.
- Expanded service visibility topics beyond `synthia/services/+/catalog`.

Needed now (documentation contract):
- Canonical topic-tree spec with:
  - ownership
  - allowed publishers/subscribers
  - retain/QoS defaults
  - implemented vs Not developed markers
