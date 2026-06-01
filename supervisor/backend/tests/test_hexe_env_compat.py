import os
import unittest
from unittest.mock import patch

from app.core.env import getenv, install_legacy_env_aliases, legacy_env_name


class TestHexeEnvCompat(unittest.TestCase):
    def test_legacy_name_maps_hexe_prefix_to_synthia_prefix(self) -> None:
        self.assertEqual(legacy_env_name("HEXE_ADMIN_TOKEN"), "SYNTHIA_ADMIN_TOKEN")
        self.assertIsNone(legacy_env_name("PLATFORM_NAME"))

    def test_getenv_prefers_hexe_value_over_legacy_value(self) -> None:
        with patch.dict(os.environ, {"HEXE_ADMIN_TOKEN": "new", "SYNTHIA_ADMIN_TOKEN": "old"}, clear=True):
            self.assertEqual(getenv("HEXE_ADMIN_TOKEN"), "new")

    def test_getenv_reads_legacy_value_when_primary_missing(self) -> None:
        with patch.dict(os.environ, {"SYNTHIA_ADMIN_TOKEN": "old"}, clear=True):
            self.assertEqual(getenv("HEXE_ADMIN_TOKEN"), "old")

    def test_install_aliases_copies_legacy_values_without_overwriting_primary(self) -> None:
        env = {
            "SYNTHIA_ADMIN_TOKEN": "old",
            "SYNTHIA_BACKEND_HOST": "127.0.0.2",
            "HEXE_BACKEND_HOST": "127.0.0.1",
        }
        install_legacy_env_aliases(env)
        self.assertEqual(env["HEXE_ADMIN_TOKEN"], "old")
        self.assertEqual(env["HEXE_BACKEND_HOST"], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
