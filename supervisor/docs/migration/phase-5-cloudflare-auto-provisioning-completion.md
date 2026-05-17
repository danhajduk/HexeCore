# Phase 5 Cloudflare Auto-Provisioning Completion

Completed on 03/20/2026

## Status

Phase 5 is implemented for the V1 single-owner platform-managed model.

Delivered:

- Cloudflare API integration models and client wrapper
- secure token-reference based Cloudflare settings
- deterministic managed tunnel naming: `hexe-core-<core-id>`
- idempotent tunnel lookup or creation
- tunnel configuration push through the Cloudflare configurations API
- idempotent DNS reconciliation for the canonical UI and API hostnames
- persisted provisioning state and operator-facing status
- live provision and dry-run API actions
- Edge Gateway UI support for token refs, dry-run, provision, and status feedback
- Supervisor-managed `cloudflared` connector runtime

## Verification

Verified in this phase:

- `cd backend && PYTHONPATH=. .venv/bin/pytest -q tests/test_cloudflare_client.py tests/test_edge_gateway_api.py`
- `cd backend && PYTHONPATH=. .venv/bin/pytest -q tests/test_platform_identity.py`
- `python3 -m py_compile backend/app/edge/service.py backend/app/edge/router.py backend/app/edge/cloudflare_client.py backend/tests/test_cloudflare_client.py backend/tests/test_edge_gateway_api.py`
- `cd frontend && npm run build`

Coverage includes:

- tunnel lookup and tunnel creation
- tunnel configuration updates
- DNS upsert behavior
- API error mapping
- dry-run validation
- first-time provision
- repeat provision idempotency
- status projection
- stable `core_id` hostname derivation
- frontend compile/build for the updated Edge Gateway UI

## Notes

This phase keeps the earlier Phase 4 boundary in place:

- Core owns desired Cloudflare and public-edge state
- Supervisor owns host-local runtime realization
- V1 remains single-owner and platform-managed only

Automated verification covers the Core-side configuration and Supervisor runtime contract, but it does not run a live external Cloudflare connectivity test as part of the backend suite.

## Future Work

Still out of scope after Phase 5:

- bring-your-own-domain
- per-user or per-tenant Cloudflare ownership
- user-linked Cloudflare OAuth flows
- multi-account or multi-zone selection
- multi-owner policy and approval workflows
