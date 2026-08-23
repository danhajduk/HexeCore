from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_openapi_path_snapshot_is_current_and_forbidden_job_routes_are_absent() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "tools/update_openapi_snapshot.py", "--check"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stdout + result.stderr
