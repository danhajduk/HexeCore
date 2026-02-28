from __future__ import annotations

import unittest

from app.store.models import ReleaseManifest


class TestReleaseManifestCompatibilityAdapter(unittest.TestCase):
    def test_legacy_top_level_fields_backfill_nested_compatibility(self) -> None:
        manifest = ReleaseManifest(
            id="addon_x",
            name="Addon X",
            version="1.0.0",
            core_min_version="0.1.0",
            core_max_version="0.3.0",
            dependencies=["dep_a"],
            conflicts=["bad_a"],
            checksum="abc123",
            publisher_id="pub-1",
            permissions=["filesystem.read"],
            signature={"publisher_id": "pub-1", "signature": "c2ln"},
        )
        self.assertEqual(manifest.compatibility.core_min_version, "0.1.0")
        self.assertEqual(manifest.compatibility.core_max_version, "0.3.0")
        self.assertEqual(manifest.compatibility.dependencies, ["dep_a"])
        self.assertEqual(manifest.compatibility.conflicts, ["bad_a"])

    def test_nested_compatibility_is_canonical(self) -> None:
        manifest = ReleaseManifest(
            id="addon_y",
            name="Addon Y",
            version="1.0.0",
            core_min_version="0.0.1",
            core_max_version="0.9.9",
            dependencies=["wrong_dep"],
            conflicts=["wrong_conflict"],
            checksum="abc123",
            publisher_id="pub-1",
            permissions=["filesystem.read"],
            signature={"publisher_id": "pub-1", "signature": "c2ln"},
            compatibility={
                "core_min_version": "0.2.0",
                "core_max_version": "0.4.0",
                "dependencies": ["dep_real"],
                "conflicts": ["conflict_real"],
            },
        )
        self.assertEqual(manifest.core_min_version, "0.2.0")
        self.assertEqual(manifest.core_max_version, "0.4.0")
        self.assertEqual(manifest.dependencies, ["dep_real"])
        self.assertEqual(manifest.conflicts, ["conflict_real"])


if __name__ == "__main__":
    unittest.main()
