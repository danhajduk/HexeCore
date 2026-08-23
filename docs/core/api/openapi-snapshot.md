# OpenAPI Path Snapshot

Status: Implemented

`openapi-paths.snapshot.json` is the deterministic route snapshot for the Core FastAPI app. It records each OpenAPI path with its supported methods.

Dynamic node/addon proxy catch-all routes are intentionally excluded from this generated contract. They remain runtime routes, but they are not stable generated-client operations and would otherwise create duplicate OpenAPI operation IDs across multi-method proxy handlers.

Intentional API changes:

```bash
python tools/update_openapi_snapshot.py --write
python tools/update_openapi_snapshot.py --check
```

The snapshot check also fails if removed job ownership endpoints reappear, including scheduler job routes, job lease routes, worker routes, and per-job budget usage-report routes. Core may keep internal scheduler health/configuration routes, but it must not expose job queueing, job leasing, worker execution, or per-job usage-report APIs.

The same check fails if FastAPI emits duplicate OpenAPI operation ID warnings.
