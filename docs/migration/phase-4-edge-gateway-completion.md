# Phase 4 Edge Gateway Completion

Completed on 2026-03-20

## Delivered

- stable persisted `core_id` generation and public hostname derivation
- platform metadata now exposes `core_id`, `public_ui_hostname`, and `public_api_hostname`
- new edge gateway domain models, store, service, Cloudflare renderer, and API routes
- V1 single-owner Cloudflare settings and dry-run validation
- Core-owned UI/API publications derived from `core_id`
- operator-defined publications constrained to the platform-owned domain
- supervisor-side `cloudflared` config/runtime state adapter
- Edge Gateway admin UI under `/settings/edge`
- targeted backend tests and frontend build verification

## Hostname Model

- UI: `<core-id>.hexe-ai.com`
- API: `api.<core-id>.hexe-ai.com`

`core_id` remains stable after first generation and is persisted in Core settings.

## Ownership Model

Phase 4 remains intentionally V1 single-owner only:

- one Cloudflare owner
- one account context
- one zone context
- one managed domain base: `hexe-ai.com`

## Remaining Future Work

- real process-level `cloudflared` lifecycle management instead of config/runtime placeholders only
- public request forwarding routes for edge-published targets when external ingress activation is turned on
- user-owned domains and multi-tenant Cloudflare ownership models
- richer publication editing UX and deeper health probing
