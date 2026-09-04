from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.system.supervisor_local_source import SupervisorLocalSourceGate, SupervisorLocalSourceGateConfig


class _GitScript:
    def __init__(self, *, counts: str = "0\t0", dirty: str = "", fetch_returncode: int = 0, upstream: str | None = "origin/main") -> None:
        self.counts = counts
        self.dirty = dirty
        self.fetch_returncode = fetch_returncode
        self.upstream = upstream
        self.calls: list[list[str]] = []

    def __call__(self, _source_root: Path, args: list[str], _timeout_s: float) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        if args == ["rev-parse", "--is-inside-work-tree"]:
            return self._ok("true\n")
        if args == ["rev-parse", "--show-toplevel"]:
            return self._ok("/tmp/repo\n")
        if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return self._ok("main\n")
        if args == ["rev-parse", "HEAD"]:
            return self._ok("local-sha\n")
        if args == ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]:
            return self._ok(f"{self.upstream}\n") if self.upstream else self._fail("no upstream")
        if args == ["fetch", "--quiet", "--prune"]:
            return self._ok("") if self.fetch_returncode == 0 else self._fail("https://token@example.invalid/repo.git")
        if args == ["rev-parse", "origin/main"]:
            return self._ok("remote-sha\n")
        if args == ["status", "--porcelain", "--untracked-files=all"]:
            return self._ok(self.dirty)
        if args == ["rev-list", "--left-right", "--count", "HEAD...origin/main"]:
            return self._ok(f"{self.counts}\n")
        return self._fail("unexpected command")

    @staticmethod
    def _ok(stdout: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["git"], returncode=0, stdout=stdout, stderr="")

    @staticmethod
    def _fail(stderr: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["git"], returncode=1, stdout="", stderr=stderr)


class TestSupervisorLocalSourceGate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.source_root = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _gate(self, script: _GitScript, *, mirror_ok: bool = True) -> dict[str, object]:
        return SupervisorLocalSourceGate(
            source_root=self.source_root,
            config=SupervisorLocalSourceGateConfig(enabled=True, fetch_enabled=True, fetch_timeout_s=20.0),
            git_runner=script,
            mirror_checker=lambda: (mirror_ok, None if mirror_ok else "mirror_drift_detected"),
        ).inspect()

    def test_config_defaults_to_enabled_fetching(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = SupervisorLocalSourceGateConfig.from_env()

        self.assertTrue(config.enabled)
        self.assertTrue(config.fetch_enabled)
        self.assertEqual(config.fetch_timeout_s, 20.0)

    def test_config_reads_env_and_clamps_timeout(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HEXE_SUPERVISOR_LOCAL_GIT_CHECK_ENABLED": "false",
                "HEXE_SUPERVISOR_LOCAL_GIT_FETCH_ENABLED": "false",
                "HEXE_SUPERVISOR_LOCAL_GIT_FETCH_TIMEOUT_S": "500",
            },
            clear=True,
        ):
            config = SupervisorLocalSourceGateConfig.from_env()

        self.assertFalse(config.enabled)
        self.assertFalse(config.fetch_enabled)
        self.assertEqual(config.fetch_timeout_s, 120.0)

    def test_classifies_clean_current_source(self) -> None:
        result = self._gate(_GitScript())

        self.assertEqual(result["classification"], "current")
        self.assertEqual(result["reason"], "local_source_current")
        self.assertTrue(result["auto_update_allowed"])
        self.assertEqual(result["ahead"], 0)
        self.assertEqual(result["behind"], 0)
        self.assertTrue(result["mirror_drift_ok"])

    def test_classifies_behind_ahead_and_diverged(self) -> None:
        cases = [
            ("0\t2", "behind", "local_behind_upstream"),
            ("2\t0", "ahead", "local_ahead_of_upstream"),
            ("1\t2", "diverged", "local_and_upstream_diverged"),
        ]
        for counts, classification, reason in cases:
            with self.subTest(counts=counts):
                result = self._gate(_GitScript(counts=counts))
                self.assertEqual(result["classification"], classification)
                self.assertEqual(result["reason"], reason)
                self.assertFalse(result["auto_update_allowed"])

    def test_classifies_dirty_before_ahead_behind(self) -> None:
        result = self._gate(_GitScript(counts="0\t0", dirty=" M supervisor/backend/app/main.py\n?? supervisor/new.py\n"))

        self.assertEqual(result["classification"], "dirty")
        self.assertEqual(result["reason"], "working_tree_dirty")
        self.assertEqual(result["dirty_count"], 2)

    def test_classifies_missing_upstream_and_not_git(self) -> None:
        no_upstream = self._gate(_GitScript(upstream=None))
        self.assertEqual(no_upstream["classification"], "unknown")
        self.assertEqual(no_upstream["reason"], "upstream_missing")

        def not_git(_source_root: Path, args: list[str], _timeout_s: float) -> subprocess.CompletedProcess[str]:
            if args == ["rev-parse", "--is-inside-work-tree"]:
                return subprocess.CompletedProcess(args=["git"], returncode=1, stdout="", stderr="fatal")
            return subprocess.CompletedProcess(args=["git"], returncode=1, stdout="", stderr="")

        result = SupervisorLocalSourceGate(
            source_root=self.source_root,
            config=SupervisorLocalSourceGateConfig(),
            git_runner=not_git,
            mirror_checker=lambda: (True, None),
        ).inspect()
        self.assertEqual(result["classification"], "not_git")
        self.assertEqual(result["reason"], "source_path_is_not_git_checkout")

    def test_classifies_fetch_failure_without_storing_remote_url(self) -> None:
        result = self._gate(_GitScript(fetch_returncode=1))

        self.assertEqual(result["classification"], "fetch_failed")
        self.assertEqual(result["reason"], "fetch_failed")
        self.assertEqual(result["fetch_exit_code"], 1)
        self.assertNotIn("example.invalid", str(result))
        self.assertNotIn("token", str(result).lower())

    def test_classifies_fetch_timeout_as_fetch_failed(self) -> None:
        def timeout_runner(_source_root: Path, args: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
            if args == ["fetch", "--quiet", "--prune"]:
                raise subprocess.TimeoutExpired(cmd=["git", *args], timeout=timeout_s)
            return _GitScript()(_source_root, args, timeout_s)

        result = SupervisorLocalSourceGate(
            source_root=self.source_root,
            config=SupervisorLocalSourceGateConfig(),
            git_runner=timeout_runner,
            mirror_checker=lambda: (True, None),
        ).inspect()

        self.assertEqual(result["classification"], "fetch_failed")
        self.assertEqual(result["reason"], "fetch_failed")
        self.assertEqual(result["fetch_exit_code"], 124)

    def test_classifies_mirror_drift_as_unknown_blocker(self) -> None:
        result = self._gate(_GitScript(), mirror_ok=False)

        self.assertEqual(result["classification"], "unknown")
        self.assertEqual(result["reason"], "mirror_drift_detected")
        self.assertEqual(result["auto_update_blocker"], "mirror_drift_detected")


if __name__ == "__main__":
    unittest.main()
