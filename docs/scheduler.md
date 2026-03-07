# Scheduler Documentation

## Purpose

Scheduler coordinates background job leasing and execution orchestration between core and workers/addons.

## Main Components

- `app/system/scheduler/engine.py`: scheduling engine
- `store.py`, `queue_store.py`: in-memory/live state
- `history.py`: SQLite-backed history and decision logs
- `queue_persist.py`: queue persistence database layer
- `router.py`: API endpoints for job/lease/queue/history

## Job and Lease Model

Implemented:
- submit jobs with priority and optional idempotency/uniqueness behavior
- workers request leases
- heartbeat extends leases
- complete/report/revoke endpoints update lease and history state

## Queue/Trigger Model

- explicit queue endpoints under `/queue/*`
- dispatchable jobs endpoint for worker polling
- debug queue endpoint gated by config flag

## Retry Behavior

- scheduler exposes mechanisms to report failures and lease outcomes
- fine-grained retry policy strategy is partially implicit in engine logic and not fully documented as a standalone policy API

## Persistence

- scheduler history persisted to SQLite
- queue persistence uses SQLite store file (`var/scheduler_queue.db` default)

## Integrations

- integrated into backend app state and router mount at `/api/system/scheduler`
- history cleanup background loop runs daily

## Not Developed

- Distributed scheduler coordination across nodes
- Fully declarative retry-policy management API
