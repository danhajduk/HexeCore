# Archived Document

Status: Outdated
Replaced by: docs/document-index.md (canonical set)
Preserved for historical reference only.

# MQTT Apply and Rollback Pipeline

Last Updated: 2026-03-09 09:08 US/Pacific

## Core Pipeline

Core-side implementation:
- `backend/app/system/mqtt/apply_pipeline.py`

Behavior:
- validate generated artifacts before apply
- stage artifacts before promotion
- preserve backup of live artifacts
- apply runtime reload/restart through runtime boundary
- rollback to backup when runtime remains unhealthy after apply
- triggered on startup reconcile and on authority state changes (grant/principal update hook path)

## Audit Integration

Pipeline emits audit records through:
- `backend/app/system/mqtt/authority_audit.py`

Events include:
- apply success
- validation failure
- rollback on runtime failure

## Operator Correlation (Phase 2)

Pipeline outcomes are surfaced in setup summary:
- `reconciliation.last_reconcile_status`
- `reconciliation.last_reconcile_error`
- `reconciliation.last_runtime_state`

Degraded/recovery triage should correlate:
- `/api/system/mqtt/setup-summary`
- `/api/system/mqtt/audit`
- `/api/system/mqtt/observability`
