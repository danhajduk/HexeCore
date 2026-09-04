from __future__ import annotations

import base64
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from app.supervisor.update_package import (
    SupervisorUpdatePackageError,
    build_supervisor_update_package,
    decode_update_package_request,
    extract_update_package_archive,
    validate_update_package_manifest,
)


class TestSupervisorUpdatePackage(unittest.TestCase):
    def _source_root(self, tmp: str) -> Path:
        root = Path(tmp) / "source"
        (root / "backend" / "app").mkdir(parents=True)
        (root / "backend" / ".venv").mkdir(parents=True)
        (root / "backend" / "var").mkdir(parents=True)
        (root / "config").mkdir()
        (root / "scripts").mkdir()
        (root / "systemd" / "user").mkdir(parents=True)
        (root / "backend" / "app" / "main.py").write_text("print('ok')\n", encoding="utf-8")
        (root / "backend" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        (root / "backend" / ".venv" / "secret.py").write_text("ignore\n", encoding="utf-8")
        (root / "backend" / "var" / "runtime.log").write_text("ignore\n", encoding="utf-8")
        (root / "config" / "supervisor.json").write_text(
            '{ "schema_version": "hexe.supervisor.config.v1", "version": "0.6.3" }\n',
            encoding="utf-8",
        )
        (root / "scripts" / "update.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (root / "scripts" / "update.sh").chmod(0o755)
        (root / "systemd" / "user" / "hexe-supervisor.service.in").write_text("ExecStart=@INSTALL_DIR@\n", encoding="utf-8")
        (root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
        return root

    def test_build_package_excludes_runtime_artifacts_and_generates_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_supervisor_update_package(self._source_root(tmp), source_version="0.6.3", commit_sha="abc123")

        paths = {item["path"] for item in package.manifest["files"]}
        self.assertIn("backend/app/main.py", paths)
        self.assertIn("config/supervisor.json", paths)
        self.assertIn("scripts/update.sh", paths)
        self.assertNotIn("backend/.venv/secret.py", paths)
        self.assertNotIn("backend/var/runtime.log", paths)
        self.assertEqual(hashlib.sha256(package.archive).hexdigest(), package.archive_sha256)
        self.assertEqual(package.manifest["source_version"], "0.6.3")
        self.assertEqual(package.manifest["commit_sha"], "abc123")

    def test_decode_rejects_archive_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_supervisor_update_package(self._source_root(tmp))
            payload = package.to_request_payload()
            payload["package_archive_sha256"] = "0" * 64

            with self.assertRaisesRegex(SupervisorUpdatePackageError, "package_archive_checksum_mismatch"):
                decode_update_package_request(payload)

    def test_manifest_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_supervisor_update_package(self._source_root(tmp))
            manifest = copy.deepcopy(package.manifest)
            manifest["files"][0]["path"] = "../outside.py"

            with self.assertRaisesRegex(SupervisorUpdatePackageError, "package_path_escape"):
                validate_update_package_manifest(manifest)

    def test_decode_rejects_archive_manifest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_supervisor_update_package(self._source_root(tmp))
            payload = package.to_request_payload()
            payload["package_manifest"] = copy.deepcopy(package.manifest)
            payload["package_manifest"]["source_version"] = "tampered"

            with self.assertRaisesRegex(SupervisorUpdatePackageError, "package_manifest_digest_mismatch"):
                decode_update_package_request(payload)

    def test_extract_package_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_supervisor_update_package(self._source_root(tmp))
            payload = package.to_request_payload()
            manifest, archive = decode_update_package_request(payload)
            destination = Path(tmp) / "dest"

            written = extract_update_package_archive(manifest, archive, destination)

            self.assertTrue((destination / "backend" / "app" / "main.py").exists())
            self.assertTrue((destination / "config" / "supervisor.json").exists())
            self.assertTrue((destination / "scripts" / "update.sh").exists())
            self.assertGreaterEqual(len(written), 3)

    def test_decode_rejects_invalid_base64(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = build_supervisor_update_package(self._source_root(tmp))
            payload = package.to_request_payload()
            payload["package_archive_base64"] = base64.b64encode(package.archive).decode("ascii")[:-2] + "**"

            with self.assertRaisesRegex(SupervisorUpdatePackageError, "package_archive_base64_invalid"):
                decode_update_package_request(payload)


if __name__ == "__main__":
    unittest.main()
