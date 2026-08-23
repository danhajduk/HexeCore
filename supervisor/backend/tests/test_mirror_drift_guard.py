from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_core_supervisor_mirror_drift_guard_passes() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "tools/check_mirror_drift.py"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stdout + result.stderr
