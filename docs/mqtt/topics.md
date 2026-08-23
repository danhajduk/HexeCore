# MQTT Topic Families

This document describes the canonical MQTT topic families verified in the current runtime code.

The active platform MQTT topic root is `hexe/...`.

Primary code:
- `backend/app/system/mqtt/topic_families.py`

## Canonical Topic Root

Status: Implemented

- Platform-owned MQTT topics use the `hexe/` root.
- Topics outside `hexe/` are treated as `external` by the topic-family classifier.

## Reserved Topic Families

Status: Implemented

The current code recognizes these reserved top-level families under `hexe/`:

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

The current bootstrap topic constant is `hexe/bootstrap/core`.

Bootstrap listener note:

- retained bootstrap discovery for node onboarding is served over the bootstrap MQTT listener
- default bootstrap listener port: `1884`
- default operational MQTT listener port: `1883`

## Topic Classification

Status: Implemented

- Empty topics are `invalid`.
- Non-`hexe/` topics are `external`.
- `hexe/<family>/...` is classified by its second path segment when that family is reserved.
- Unrecognized `hexe/*` families are classified as `hexe_other`.

## Scoped Topic Helpers

Status: Implemented

- Addon-scoped topics are recognized under `hexe/addons/<addon_id>/...`.
- Node-scoped topics are recognized under `hexe/nodes/<node_id>/...`.
- Policy topics are recognized only when they match `hexe/policy/(grants|revocations)/<id>`.

## Reserved Prefixes

Status: Implemented

Reserved prefix checks currently cover:

- `hexe/bootstrap/`
- `hexe/runtime/`
- `hexe/system/`
- `hexe/core/`
- `hexe/supervisor/`
- `hexe/scheduler/`
- `hexe/policy/`
- `hexe/telemetry/`
- `hexe/events/`
- `hexe/remote/`
- `hexe/bridges/`
- `hexe/import/`

The canonical reserved-prefix list also includes `hexe/#` and `$SYS/#`.

## See Also

- [mqtt-platform.md](./mqtt-platform.md)
- [notifications.md](./notifications.md)
- [../fastapi/auth-and-identity.md](../fastapi/auth-and-identity.md)
