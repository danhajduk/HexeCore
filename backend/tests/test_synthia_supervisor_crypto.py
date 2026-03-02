from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from synthia_supervisor.crypto import CryptoError, _load_publishers_registry


class TestSynthiaSupervisorCrypto(unittest.TestCase):
    def test_load_publishers_registry_uses_install_root_runtime_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            install_root = Path(tmpdir) / "install"
            fake_module = install_root / "backend" / "synthia_supervisor" / "crypto.py"
            fake_module.parent.mkdir(parents=True, exist_ok=True)

            target = (
                install_root
                / "runtime"
                / "store"
                / "cache"
                / "official"
                / "publishers.json"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"publishers": []}), encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                with patch("synthia_supervisor.crypto.__file__", str(fake_module)):
                    payload = _load_publishers_registry()

        self.assertEqual(payload, {"publishers": []})

    def test_load_publishers_registry_reports_default_path_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            install_root = Path(tmpdir) / "install"
            fake_module = install_root / "backend" / "synthia_supervisor" / "crypto.py"
            fake_module.parent.mkdir(parents=True, exist_ok=True)
            expected = (
                install_root
                / "runtime"
                / "store"
                / "cache"
                / "official"
                / "publishers.json"
            )

            with patch.dict(os.environ, {}, clear=True):
                with patch("synthia_supervisor.crypto.__file__", str(fake_module)):
                    with self.assertRaises(CryptoError) as ctx:
                        _load_publishers_registry()

        self.assertIn(str(expected), str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
