# Supervisor Workload Admission

Status: Implemented

This document defines the Supervisor-aware host readiness context exposed to Core.

## Source Of Truth

- `backend/app/supervisor/models.py`
- `backend/app/supervisor/service.py`
- `backend/app/supervisor/router.py`

## Purpose

- Give Core a host-runtime readiness view from Supervisor.
- Reuse Supervisor resource state and managed-node health instead of duplicating host-local checks in Core.
- Keep host-local runtime ownership in Supervisor.

## API Surface

- `GET /api/supervisor/admission`

Current response fields:

- `admission_state`
- `execution_host_ready`
- `unavailable_reason`
- `host_busy_rating`
- `total_capacity_units`
- `available_capacity_units`
- `managed_node_count`
- `healthy_managed_node_count`

## Current Integration

Status: Implemented

- Core can inspect Supervisor admission context before asking Supervisor to realize host-local runtime intent.
- `execution_host_ready` and `available_capacity_units` summarize whether the host can accept more local runtime work.
- Managed runtime counts and health are Supervisor-owned observations.

## Boundary

- Core does not own job queueing, job leasing, or worker execution.
- Supervisor supplies host-runtime readiness and execution-target health.
- Nodes remain the canonical external execution layer.
