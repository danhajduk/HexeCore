# MQTT Observability Foundation

Last Updated: 2026-03-09 09:08 US/Pacific

## Store

Implementation:
- `backend/app/system/mqtt/observability_store.py`
- SQLite default path: `var/mqtt_observability.db`

## Captured Event Categories

Phase 1 foundation captures:
- connection/auth lifecycle issues from MQTT manager callbacks
  - `connection_failed`
  - `disconnect_error`
  - `connection_established`
- denied topic attempts from authority approval validation
  - `denied_topic_attempt`
- broker/setup readiness issues
  - `broker_readiness_issue`
- runtime health telemetry snapshots from supervision loop
  - `broker_health_telemetry`
  - metadata includes `connection_count`, `auth_failures`, `reconnect_spikes`, and observed `denied_topic_attempts`

## Intended Use

This provides the metadata baseline for future noisy-client detection and policy automation.
Automated enforcement is not implemented in Phase 1.

Phase 2 implemented usage:
- noisy-client evaluator reads runtime counters + denied-topic attempts and updates principal noisy states
- manual noisy-client actions are exposed via admin API and logged in authority audit
