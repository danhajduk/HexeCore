# Worker Runtime

This document describes the implemented worker runtime used with the scheduler subsystem.

Primary code:
- `backend/app/system/worker/runner.py`
- `backend/app/system/worker/registry.py`

## Purpose

Status: Implemented

- Workers request leases from the scheduler.
- Workers heartbeat active leases while executing jobs.
- Workers complete or fail leases with result payloads.
- The current repository includes a simple built-in handler registry for local worker execution.

## Boundary

Status: Implemented

- The scheduler remains the Core admission/orchestration boundary.
- Worker runners are execution clients that act after Core has admitted work.
- This current local worker path is a compatibility/runtime helper, not the final host-runtime ownership model.

## Worker Runner Configuration

Status: Implemented

`WorkerConfig` currently supports:

- `base_url`
- `worker_id`
- `heartbeat_interval_s`
- `jitter_s`
- `max_units`
- `timeout_s`

The runner also exposes a CLI entrypoint with matching flags:

- `--base-url`
- `--worker-id`
- `--heartbeat-interval`
- `--max-units`
- `--timeout`

## Scheduler Interaction

Status: Implemented

The worker runner currently uses these scheduler routes:

- `POST /api/system/scheduler/leases/request`
- `POST /api/system/scheduler/leases/{lease_id}/heartbeat`
- `POST /api/system/scheduler/leases/{lease_id}/complete`

Behavior:

- denied lease requests back off using `retry_after_ms`
- granted leases start a background heartbeat loop
- completion submits either `completed` or `failed`
- heartbeat failures are tolerated by allowing the server-side lease to expire naturally

## Handler Registry

Status: Implemented

Built-in handlers currently include:

- `helloworld.noop`
- `helloworld.sleep`
- `helloworld.cpu`

Alias names are also accepted:

- `noop`
- `sleep`
- `cpu`

## Execution Model

Status: Implemented

- `run_once()` requests one lease, executes its handler, and reports completion.
- `run_forever()` continuously polls for new work.
- CPU-heavy execution uses `asyncio.to_thread(...)` for local threaded work simulation.

## Current Scope

Status: Partially implemented

- The current worker subsystem is a concrete scheduler client/runtime helper.
- Advanced worker fleet management, remote deployment, and richer handler packaging are not verifiable from the current repository state.
- Host-local runtime authority is expected to move toward Supervisor over later migration tasks.

## See Also

- [../scheduler/job-model.md](../scheduler/job-model.md)
- [../fastapi/api-reference.md](../fastapi/api-reference.md)
- [../architecture.md](../architecture.md)
