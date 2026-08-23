from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.store import router_legacy
from app.store.router import StoreAuditLogStore, build_store_router


class _FakeRegistry:
    def __init__(self) -> None:
        self.addons = {}
        self.enabled = {}

    def is_enabled(self, addon_id: str) -> bool:
        return self.enabled.get(addon_id, True)

    def set_enabled(self, addon_id: str, enabled: bool) -> None:
        self.enabled[addon_id] = enabled


def _route_signature(router) -> list[tuple[str, tuple[str, ...], bool, str]]:  # noqa: ANN001
    signatures: list[tuple[str, tuple[str, ...], bool, str]] = []
    for route in router.routes:
        path = str(getattr(route, "path", ""))
        methods = tuple(sorted(str(method) for method in getattr(route, "methods", []) or []))
        include_in_schema = bool(getattr(route, "include_in_schema", True))
        name = str(getattr(route, "name", ""))
        signatures.append((path, methods, include_in_schema, name))
    return sorted(signatures)


class TestStoreRouterComposition(unittest.TestCase):
    def test_domain_composed_router_preserves_legacy_route_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_audit = StoreAuditLogStore(str(Path(tmpdir) / "legacy_audit.db"))
            composed_audit = StoreAuditLogStore(str(Path(tmpdir) / "composed_audit.db"))

            legacy_router = router_legacy.build_store_router(_FakeRegistry(), legacy_audit)
            composed_router = build_store_router(_FakeRegistry(), composed_audit)

        self.assertEqual(_route_signature(composed_router), _route_signature(legacy_router))


if __name__ == "__main__":
    unittest.main()
