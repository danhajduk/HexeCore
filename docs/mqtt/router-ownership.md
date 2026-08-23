# MQTT Router Ownership

Status: Implemented

Core composes the MQTT API through `backend/app/system/mqtt/router.py`. The behavior-preserving source implementation lives in `backend/app/system/mqtt/router_legacy.py`; `backend/app/system/mqtt/domains/` assigns those routes to explicit ownership slices without changing public paths, aliases, auth behavior, or response shapes.

Domain ownership:

- `setup`: status, setup test/apply, setup summary, health, bootstrap publish, setup-state, restart, reload, and test publish endpoints
- `runtime`: broker runtime health, sessions, topics, stats history, mitigations, start/stop/init/rebuild, and runtime config aliases
- `debug`: debug subscribe/publish/unsubscribe, notification test flow, ACL/config/authority inspection, effective access, and topic validation
- `provisioning`: addon MQTT registration approval, provisioning, and revocation
- `bridge_grants`: trusted node bridge grant request, review, approval, provisioning, credential claim, and revocation
- `grants`: addon grant list and detail endpoints
- `principals`: principal detail/actions, generic users, users import/export/update/delete, credential rotation, and noisy-client controls
- `observability`: MQTT observability events, node-domain decisions, and authority audit endpoints

`tests/test_mqtt_router_composition.py` verifies that the composed router preserves the same route path, method, schema visibility, and handler-name surface as the legacy source router.
