from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.system.supervisors import _clean_text, _repo_root, _supervisor_package_source_root


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_timeout_s(name: str, default: float) -> float:
    raw = str(os.getenv(name, str(default))).strip()
    try:
        return min(max(1.0, float(raw)), 120.0)
    except Exception:
        return default


@dataclass(frozen=True)
class SupervisorLocalSourceGateConfig:
    enabled: bool = True
    fetch_enabled: bool = True
    fetch_timeout_s: float = 20.0

    @classmethod
    def from_env(cls) -> "SupervisorLocalSourceGateConfig":
        return cls(
            enabled=_env_bool("HEXE_SUPERVISOR_LOCAL_GIT_CHECK_ENABLED", True),
            fetch_enabled=_env_bool("HEXE_SUPERVISOR_LOCAL_GIT_FETCH_ENABLED", True),
            fetch_timeout_s=_env_timeout_s("HEXE_SUPERVISOR_LOCAL_GIT_FETCH_TIMEOUT_S", 20.0),
        )


GitRunner = Callable[[Path, list[str], float], subprocess.CompletedProcess[str]]
MirrorChecker = Callable[[], tuple[bool, str | None]]


class SupervisorLocalSourceGate:
    def __init__(
        self,
        *,
        source_root: Path | None = None,
        config: SupervisorLocalSourceGateConfig | None = None,
        git_runner: GitRunner | None = None,
        mirror_checker: MirrorChecker | None = None,
    ) -> None:
        self.source_root = (source_root or _supervisor_package_source_root()).expanduser()
        self.config = config or SupervisorLocalSourceGateConfig.from_env()
        self.git_runner = git_runner or self._run_git
        self.mirror_checker = mirror_checker or self._check_mirror_drift

    def inspect(self) -> dict[str, object]:
        checked_at = _utcnow_iso()
        result: dict[str, object] = {
            "schema_version": "1",
            "source_root": str(self.source_root),
            "checked_at": checked_at,
            "fetch_enabled": self.config.fetch_enabled,
            "fetch_attempted": False,
            "fetch_ok": None,
            "fetch_checked_at": None,
            "mirror_drift_ok": None,
            "auto_update_allowed": False,
        }
        if not self.config.enabled:
            return self._finish(result, "unknown", "local_git_check_disabled")
        if not self.source_root.exists() or not self.source_root.is_dir():
            return self._finish(result, "not_git", "source_root_missing")

        inside = self._git(["rev-parse", "--is-inside-work-tree"])
        if inside.returncode != 0 or _clean_text(inside.stdout) != "true":
            return self._finish(result, "not_git", "source_path_is_not_git_checkout")

        worktree = self._git_text(["rev-parse", "--show-toplevel"])
        branch = self._git_text(["rev-parse", "--abbrev-ref", "HEAD"])
        head = self._git_text(["rev-parse", "HEAD"])
        upstream = self._git_text(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
        result.update(
            {
                "worktree_root": worktree,
                "branch": branch,
                "head": head,
                "upstream": upstream,
            }
        )
        if not upstream:
            return self._finish(result, "unknown", "upstream_missing")

        if self.config.fetch_enabled:
            result["fetch_attempted"] = True
            result["fetch_checked_at"] = _utcnow_iso()
            fetch = self._git(["fetch", "--quiet", "--prune"], timeout_s=self.config.fetch_timeout_s)
            result["fetch_ok"] = fetch.returncode == 0
            if fetch.returncode != 0:
                result["fetch_exit_code"] = fetch.returncode
                return self._finish(result, "fetch_failed", "fetch_failed")

        upstream_head = self._git_text(["rev-parse", upstream])
        result["upstream_head"] = upstream_head

        status = self._git(["status", "--porcelain", "--untracked-files=all"])
        if status.returncode != 0:
            return self._finish(result, "unknown", "git_status_failed")
        dirty_lines = [line for line in (status.stdout or "").splitlines() if line.strip()]
        result["dirty"] = bool(dirty_lines)
        result["dirty_count"] = len(dirty_lines)
        if dirty_lines:
            return self._finish(result, "dirty", "working_tree_dirty")

        counts = self._git_text(["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
        ahead, behind = self._parse_counts(counts)
        result["ahead"] = ahead
        result["behind"] = behind
        if ahead is None or behind is None:
            return self._finish(result, "unknown", "ahead_behind_unknown")
        if ahead > 0 and behind > 0:
            return self._finish(result, "diverged", "local_and_upstream_diverged")
        if behind > 0:
            return self._finish(result, "behind", "local_behind_upstream")
        if ahead > 0:
            return self._finish(result, "ahead", "local_ahead_of_upstream")

        mirror_ok, mirror_reason = self.mirror_checker()
        result["mirror_drift_ok"] = mirror_ok
        if not mirror_ok:
            return self._finish(result, "unknown", mirror_reason or "mirror_drift_detected")
        return self._finish(result, "current", "local_source_current")

    def _finish(self, result: dict[str, object], classification: str, reason: str) -> dict[str, object]:
        result["classification"] = classification
        result["reason"] = reason
        result["auto_update_allowed"] = classification == "current"
        if classification != "current":
            result["auto_update_blocker"] = reason
        return result

    def _git(self, args: list[str], *, timeout_s: float = 5.0) -> subprocess.CompletedProcess[str]:
        try:
            return self.git_runner(self.source_root, args, timeout_s)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(args=["git", *args], returncode=124, stdout="", stderr="timeout")
        except Exception:
            return subprocess.CompletedProcess(args=["git", *args], returncode=1, stdout="", stderr="error")

    def _git_text(self, args: list[str]) -> str | None:
        result = self._git(args)
        text = _clean_text(result.stdout)
        return text if result.returncode == 0 and text else None

    @staticmethod
    def _run_git(source_root: Path, args: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=source_root,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )

    @staticmethod
    def _parse_counts(raw: str | None) -> tuple[int | None, int | None]:
        parts = str(raw or "").split()
        if len(parts) != 2:
            return None, None
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return None, None

    @staticmethod
    def _check_mirror_drift() -> tuple[bool, str | None]:
        repo_root = _repo_root().parent
        script = repo_root / "tools" / "check_mirror_drift.py"
        if not script.exists():
            return False, "mirror_drift_guard_unavailable"
        try:
            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=30.0,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "mirror_drift_guard_timeout"
        except Exception:
            return False, "mirror_drift_guard_failed"
        if result.returncode == 0:
            return True, None
        return False, "mirror_drift_detected"
