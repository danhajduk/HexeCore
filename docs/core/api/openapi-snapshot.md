# OpenAPI Path Snapshot

Status: Implemented

`openapi-paths.snapshot.json` is the deterministic route snapshot for the Core FastAPI app. It records each OpenAPI path with its supported methods.

Intentional API changes:

```bash
python tools/update_openapi_snapshot.py --write
python tools/update_openapi_snapshot.py --check
```

The snapshot check also fails if removed job ownership endpoints reappear, including scheduler job routes, job lease routes, worker routes, and per-job budget usage-report routes. Core may keep internal scheduler health/configuration routes, but it must not expose job queueing, job leasing, worker execution, or per-job usage-report APIs.
