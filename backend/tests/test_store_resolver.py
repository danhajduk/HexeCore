from __future__ import annotations

import unittest

from app.store.models import ReleaseManifest
from app.store.resolver import ResolverError, resolve_manifest_compatibility


def _manifest(**overrides) -> ReleaseManifest:
    base = {
        "id": "addon_a",
        "name": "Addon A",
        "version": "1.2.3",
        "core_min_version": "0.1.0",
        "core_max_version": "0.5.0",
        "dependencies": ["dep_b", "dep_a", "dep_b"],
        "conflicts": ["bad_x"],
        "checksum": "abc123",
        "publisher_id": "pub-1",
        "permissions": ["filesystem.read"],
        "signature": {"publisher_id": "pub-1", "signature": "c2ln"},
        "compatibility": {
            "core_min_version": "0.1.0",
            "core_max_version": "0.5.0",
            "dependencies": [],
            "conflicts": [],
        },
    }
    base.update(overrides)
    return ReleaseManifest(**base)


class TestStoreResolver(unittest.TestCase):
    def test_resolve_success_returns_deterministic_dependency_order(self) -> None:
        manifest = _manifest()
        result = resolve_manifest_compatibility(
            manifest,
            core_version="0.3.0",
            installed_addons={"dep_a": "1.0.0", "dep_b": "2.0.0"},
        )
        self.assertEqual(result.ordered_dependencies, ["dep_a", "dep_b"])
        self.assertEqual(result.checked_conflicts, ["bad_x"])

    def test_core_version_too_low(self) -> None:
        manifest = _manifest(core_min_version="0.4.0")
        with self.assertRaises(ResolverError) as ctx:
            resolve_manifest_compatibility(
                manifest,
                core_version="0.3.0",
                installed_addons={"dep_a": "1.0.0", "dep_b": "2.0.0"},
            )
        self.assertEqual(ctx.exception.code, "core_version_too_low")

    def test_core_version_too_high(self) -> None:
        manifest = _manifest(core_max_version="0.2.0")
        with self.assertRaises(ResolverError) as ctx:
            resolve_manifest_compatibility(
                manifest,
                core_version="0.3.0",
                installed_addons={"dep_a": "1.0.0", "dep_b": "2.0.0"},
            )
        self.assertEqual(ctx.exception.code, "core_version_too_high")

    def test_missing_dependency(self) -> None:
        manifest = _manifest(dependencies=["dep_a", "dep_missing"])
        with self.assertRaises(ResolverError) as ctx:
            resolve_manifest_compatibility(
                manifest,
                core_version="0.3.0",
                installed_addons={"dep_a": "1.0.0"},
            )
        self.assertEqual(ctx.exception.code, "dependency_missing")
        self.assertEqual(ctx.exception.details["missing_dependencies"], ["dep_missing"])

    def test_conflict_detected(self) -> None:
        manifest = _manifest(dependencies=["dep_b"], conflicts=["dep_a"])
        with self.assertRaises(ResolverError) as ctx:
            resolve_manifest_compatibility(
                manifest,
                core_version="0.3.0",
                installed_addons={"dep_a": "1.0.0", "dep_b": "2.0.0"},
            )
        self.assertEqual(ctx.exception.code, "conflict_detected")

    def test_manifest_inconsistent(self) -> None:
        manifest = _manifest(dependencies=["x"], conflicts=["x"])
        with self.assertRaises(ResolverError) as ctx:
            resolve_manifest_compatibility(
                manifest,
                core_version="0.3.0",
                installed_addons={"x": "1.0.0"},
            )
        self.assertEqual(ctx.exception.code, "manifest_inconsistent")


if __name__ == "__main__":
    unittest.main()
