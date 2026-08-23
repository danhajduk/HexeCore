#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class HealthCommand:
    label: str
    argv: list[str]
    cwd: Path = REPO_ROOT


def _python_for(root: Path) -> str:
    venv_python = root / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _commands(*, include_backend_tests: bool) -> list[HealthCommand]:
    commands = [
        HealthCommand("mirror drift guard", [sys.executable, "tools/check_mirror_drift.py"]),
        HealthCommand("environment registry", [sys.executable, "tools/check_env_registry.py", "--check-docs"]),
        HealthCommand("OpenAPI snapshot", [sys.executable, "tools/update_openapi_snapshot.py", "--check"]),
    ]
    if include_backend_tests:
        core_backend = REPO_ROOT / "core" / "backend"
        supervisor_backend = REPO_ROOT / "supervisor" / "backend"
        test_files = [
            "tests/test_mirror_drift_guard.py",
            "tests/test_env_registry.py",
            "tests/test_openapi_contract_snapshot.py",
        ]
        commands.extend(
            [
                HealthCommand(
                    "Core backend guard tests",
                    [_python_for(core_backend), "-m", "pytest", *test_files],
                    cwd=core_backend,
                ),
                HealthCommand(
                    "Supervisor backend guard tests",
                    [_python_for(supervisor_backend), "-m", "pytest", *test_files],
                    cwd=supervisor_backend,
                ),
            ]
        )
    return commands


def run_health(*, include_backend_tests: bool) -> int:
    failures: list[str] = []
    for command in _commands(include_backend_tests=include_backend_tests):
        print(f"==> {command.label}", flush=True)
        result = subprocess.run(command.argv, cwd=command.cwd, text=True)
        if result.returncode != 0:
            failures.append(command.label)
            print(f"!! {command.label} failed with exit code {result.returncode}", flush=True)
    if failures:
        print("Repo health failed: " + ", ".join(failures), flush=True)
        return 1
    print("Repo health passed.", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Core/Supervisor repository health checks.")
    parser.add_argument(
        "--skip-backend-tests",
        action="store_true",
        help="run guard scripts only; skip targeted Core/Supervisor pytest guard tests",
    )
    args = parser.parse_args()
    return run_health(include_backend_tests=not args.skip_backend_tests)


if __name__ == "__main__":
    raise SystemExit(main())
