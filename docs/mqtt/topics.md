# MQTT Topic Families

This document describes the canonical MQTT topic families verified in the current runtime code.

Primary code:
- `backend/app/system/mqtt/topic_families.py`

## Canonical Topic Root

Status: Implemented

- Platform-owned MQTT topics use the `synthia/` root.
- Topics outside `synthia/` are treated as `external` by the topic-family classifier.

## Reserved Topic Families

Status: Implemented

The current code recognizes these reserved top-level families under `synthia/`:

- `bootstrap`
- `runtime`
- `core`
- `system`
- `supervisor`
- `scheduler`
- `policy`
- `telemetry`
- `events`
- `remote`
- `bridges`
- `import`
- `services`
- `addons`
- `nodes`

The current bootstrap topic constant is `synthia/bootstrap/core`.

## Topic Classification

Status: Implemented

- Empty topics are `invalid`.
- Non-`synthia/` topics are `external`.
- `synthia/<family>/...` is classified by its second path segment when that family is reserved.
- Unrecognized `synthia/*` families are classified as `synthia_other`.

## Scoped Topic Helpers

Status: Implemented

- Addon-scoped topics are recognized under `synthia/addons/<addon_id>/...`.
- Node-scoped topics are recognized under `synthia/nodes/<node_id>/...`.
- Policy topics are recognized only when they match `synthia/policy/(grants|revocations)/<id>`.

## Reserved Prefixes

Status: Implemented

Reserved prefix checks currently cover:

- `synthia/bootstrap/`
- `synthia/runtime/`
- `synthia/system/`
- `synthia/core/`
- `synthia/supervisor/`
- `synthia/scheduler/`
- `synthia/policy/`
- `synthia/telemetry/`
- `synthia/events/`
- `synthia/remote/`
- `synthia/bridges/`
- `synthia/import/`

The canonical reserved-prefix list also includes `synthia/#` and `$SYS/#`.

## See Also

- [mqtt-platform.md](./mqtt-platform.md)
- [notifications.md](./notifications.md)
- [../fastapi/auth-and-identity.md](../fastapi/auth-and-identity.md)
