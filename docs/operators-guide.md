# Operators Guide

This document is the canonical operator runbook for current Synthia behavior.

## 1) Setup

Status: Implemented

- Verify Core is running and admin session is available.
- For MQTT setup, use setup summary and setup apply/test endpoints before enabling post-setup operations.
- Confirm runtime directories and state stores are writable (`var/`, `runtime/`).

## 2) Health Checks

Status: Implemented

Primary checks:
- `GET /api/system/stack/summary`
- `GET /api/system/mqtt/setup-summary`
- `GET /api/system/mqtt/health`
- `GET /api/system/mqtt/runtime/health`
- `GET /api/system-stats/health`

## 3) Recovery Basics

Status: Implemented

- MQTT runtime actions:
  - init/start/stop/rebuild/reload endpoints under `/api/system/mqtt/*`.
- Use audit and observability endpoints to correlate failures before force actions.
- If runtime reports `config_missing`, run setup/reconcile flow and re-check health.

## 4) Rebuild / Apply / Reconcile

Status: Implemented

- Setup apply triggers configuration/state updates and runtime pipeline hooks.
- Rebuild may enforce safety guard behavior when active non-core clients are connected.
- Startup reconciliation ensures authority/runtime artifacts are aligned.

## 5) Runtime Troubleshooting

Status: Implemented

Quick flow:
1. Check setup summary and runtime health.
2. Inspect audit trail and observability events.
3. Inspect debug effective-access/config if permission/topic failures are suspected.
4. Retry targeted runtime action (`reload`/`rebuild`) once root cause is corrected.

## 6) Scheduler and Jobs

Status: Implemented

- Verify scheduler status and queue depth through `/api/system/scheduler/status`.
- Review history stats and cleanup endpoints for retention issues.

## 7) Archived Legacy Runbooks

Status: Archived Legacy

- Earlier split MQTT Phase 1/2 runbooks were consolidated into this guide and moved to archive.

## See Also

- [MQTT Platform](./mqtt-platform.md)
- [Runtime and Supervision](./runtime-and-supervision.md)
- [API Reference](./api-reference.md)
- [Document Index](./document-index.md)
