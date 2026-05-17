# Telemetry And Usage

This document describes the canonical usage-telemetry subsystem exposed by the Core backend.

Primary code:
- `backend/app/system/telemetry/router.py`
- `backend/app/system/telemetry/store.py`

## Purpose

Status: Implemented

- Core accepts service-reported usage telemetry for addon and grant accounting.
- Core stores usage reports in a local SQLite-backed telemetry store.
- Core exposes list and aggregate views for stored usage data.

## API Surface

Status: Implemented

Mounted under `/api/telemetry`:

- `POST /usage`
- `GET /usage`
- `GET /usage/stats`

Full routes:

- `POST /api/telemetry/usage`
- `GET /api/telemetry/usage`
- `GET /api/telemetry/usage/stats`

## Write Authentication

Status: Implemented

- Telemetry ingestion requires a service token with audience `synthia-core`.
- The required scope is `telemetry.write`.
- The write endpoint resolves claims through `require_service_token(...)`.

## Usage Record Contract

Status: Implemented

Telemetry ingestion accepts:

- `service`
- `consumer_addon_id`
- `grant_id` (optional)
- `usage_units`
- `request_count`
- `period_start` (optional)
- `period_end` (optional)
- `metadata`

Stored records also include:

- `id`
- `reported_at`

## Query Surface

Status: Implemented

- `GET /api/telemetry/usage` returns recent stored items.
- Supported filters are `service`, `consumer_addon_id`, and `grant_id`.
- `limit` is constrained to `1..1000`.

- `GET /api/telemetry/usage/stats` returns aggregate totals over a bounded time window.
- `days` is constrained to `1..365`.

## Storage Model

Status: Implemented

- Usage telemetry is stored in SQLite table `telemetry_usage`.
- Indexed fields include `service`, `consumer_addon_id`, `grant_id`, and `reported_at`.

## See Also

- [api-reference.md](./api-reference.md)
- [auth-and-identity.md](./auth-and-identity.md)
- [data-and-state.md](./data-and-state.md)
