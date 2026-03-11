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

## 8) AI Node Onboarding Runbook

Status: Implemented (baseline)

Core onboarding flow:
1. Node starts onboarding via `POST /api/system/nodes/onboarding/sessions`.
2. Node receives `approval_url` and shows it to operator.
3. Operator opens approval URL and signs into Core admin session if required.
4. Operator approves or rejects onboarding.
5. Node polls finalize endpoint:
   - `GET /api/system/nodes/onboarding/sessions/{session_id}/finalize?node_nonce=...`

Finalization outcomes:
- `pending`: waiting for operator decision
- `approved`: trust activation payload returned on first successful retrieval
- `rejected`: onboarding denied by operator
- `expired`: session expired before decision/finalization
- `consumed`: trust payload already consumed (replay attempt)
- `invalid`: session or binding token mismatch

Troubleshooting checklist:
1. Verify session exists and current state in Settings -> Node Onboarding Sessions.
2. Confirm approval URL includes both `sid` and `state`.
3. Confirm node uses matching `node_nonce` during finalize.
4. If operator action fails with CSRF mismatch, ensure request origin/referer aligns with Core base URL.
5. If API returns `rate_limited`, retry after window cooldown.
6. For expired sessions, restart onboarding from session creation.

## See Also

- [MQTT Platform](./mqtt-platform.md)
- [Runtime and Supervision](./runtime-and-supervision.md)
- [API Reference](./api-reference.md)
- [Document Index](./document-index.md)
