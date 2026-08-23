# Store Router Ownership

Status: Implemented

Core composes the Store API through `backend/app/store/router.py`. That file is intentionally small: it builds the behavior-preserving source router in `backend/app/store/router_legacy.py`, then assigns routes to explicit domain routers in `backend/app/store/domains/`.

Domain ownership:

- `catalog`: `/catalog`
- `sources`: `/sources*`
- `install`: `/install`, `/update`, and `/uninstall`
- `lifecycle`: `/standalone/update`
- `status`: `/status*`
- `audit`: `/admin/audit`

`tests/test_store_router_composition.py` verifies that the composed domain router preserves the same route path, method, schema visibility, and handler-name surface as the legacy source router.
