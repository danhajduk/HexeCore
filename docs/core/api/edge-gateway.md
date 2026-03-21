# Edge Gateway

Status: Implemented for Phase 4 V1 single-owner foundations

## Overview

The Hexe Core Edge Gateway makes Core the public ingress point for the platform.

Request path:

- Client -> Cloudflare Tunnel -> Core public UI hostname
- Client -> Cloudflare Tunnel -> Core public API hostname
- Core -> local UI/API services
- Core -> Supervisor-managed runtimes
- Core -> trusted nodes through explicit later publications

## Core-ID Hostname Model

Each Core instance owns a stable persisted `core_id`.

Canonical hostnames:

- UI: `<core-id>.hexe-ai.com`
- API: `api.<core-id>.hexe-ai.com`

Rules:

- `core_id` is generated once and persisted in Core settings
- default format is 16-character lowercase hex
- hostnames are derived deterministically from `core_id`
- hostname is addressability only, not the trust mechanism

Trust still relies on stored credentials, trust tokens, governance, and service/node policy.

## Responsibilities

Core:

- owns the canonical public identity
- validates and stores publication records
- derives Core-owned UI/API hostnames
- renders desired Cloudflare tunnel ingress config
- exposes edge status, dry-run validation, and reconcile APIs

Supervisor:

- owns host-local `cloudflared` runtime state
- stores rendered runtime config on disk
- reports runtime/configured status back to Core
- does not perform multi-tenant Cloudflare selection in V1

Nodes:

- are not directly public by default
- can only be published through validated Core-managed publications
- must remain trusted before node-target publications are allowed

## Publication Model

Built-in Core-owned publications always exist logically:

- `core-ui` -> `http://127.0.0.1:8080`
- `core-api` -> `http://127.0.0.1:9001`

Additional publications are operator-defined and constrained to the platform-owned base domain.

Validated publication rules include:

- hostname must stay under `hexe-ai.com`
- Core-owned hostnames cannot be spoofed
- duplicate hostname/path combinations are rejected
- node targets must still be trusted
- supervisor runtime targets must exist
- upstream forwarding is allow-listed to local loopback targets in V1

## Security Boundaries

- Core remains the policy and publication authority
- Supervisor remains the host-local runtime authority
- edge proxy forwarding uses SSRF guards, header filtering, and bounded timeouts
- Cloudflare ownership is single-owner and platform-managed in V1
- Core-derived UI/API hostnames cannot be replaced by operator-defined publications

## Status And Observability

`GET /api/edge/status` exposes:

- public UI/API hostnames
- Cloudflare settings projection
- tunnel/configured runtime state
- publication list
- validation errors
- reconcile outcome

Edge changes emit audit events for:

- Cloudflare settings updates
- publication create/update/delete
- reconcile completion

## Cloudflare Ownership Model

Phase 4 intentionally supports only:

- one Cloudflare owner
- one Cloudflare account context
- one Cloudflare zone context
- one managed base domain: `hexe-ai.com`

Out of scope for V1:

- bring-your-own-domain
- per-tenant Cloudflare accounts
- user-owned zones
- multi-owner selection logic
