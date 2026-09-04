from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from tools.check_env_registry import ENV_PATTERNS


def _pattern_names(text: str) -> set[str]:
    names: set[str] = set()
    for pattern in ENV_PATTERNS:
        names.update(match.group(1) for match in pattern.finditer(text))
    return names


def test_environment_registry_scanner_detects_helper_reads() -> None:
    text = '''
value = _env_text("HEXE_SUPERVISOR_PUBLIC_URL")
timeout = _env_float('HEXE_SUPERVISOR_REPORT_TIMEOUT_S', 5.0)
hexe_env HEXE_SUPERVISOR_CORE_TOKEN
write_env_if_set "HEXE_SUPERVISOR_PORT" "$SUPERVISOR_PORT"
'''

    names = _pattern_names(text)

    assert "HEXE_SUPERVISOR_PUBLIC_URL" in names
    assert "HEXE_SUPERVISOR_REPORT_TIMEOUT_S" in names
    assert "HEXE_SUPERVISOR_CORE_TOKEN" in names
    assert "HEXE_SUPERVISOR_PORT" in names


def test_core_environment_registry_is_complete() -> None:
    result = subprocess.run(
        [sys.executable, "tools/check_env_registry.py", "--check-docs"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stdout + result.stderr
