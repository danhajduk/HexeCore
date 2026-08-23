from __future__ import annotations

import unittest

from app.api import system_legacy
from app.api.system import build_system_router


def _route_signature(router) -> list[tuple[str, tuple[str, ...], bool, str]]:  # noqa: ANN001
    signatures: list[tuple[str, tuple[str, ...], bool, str]] = []
    for route in router.routes:
        path = str(getattr(route, "path", ""))
        methods = tuple(sorted(str(method) for method in getattr(route, "methods", []) or []))
        include_in_schema = bool(getattr(route, "include_in_schema", True))
        name = str(getattr(route, "name", ""))
        signatures.append((path, methods, include_in_schema, name))
    return sorted(signatures)


class TestSystemRouterComposition(unittest.TestCase):
    def test_domain_composed_router_preserves_legacy_route_surface(self) -> None:
        legacy_router = system_legacy.build_system_router(registry=object())
        composed_router = build_system_router(registry=object())

        self.assertEqual(_route_signature(composed_router), _route_signature(legacy_router))


if __name__ == "__main__":
    unittest.main()
