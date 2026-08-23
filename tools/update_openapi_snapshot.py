#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "core" / "backend"
SNAPSHOT_PATH = REPO_ROOT / "docs" / "core" / "api" / "openapi-paths.snapshot.json"

FORBIDDEN_PATH_PREFIXES = (
    "/api/system/scheduler/jobs",
    "/api/system/jobs",
    "/api/system/job-lease",
    "/api/system/job-leases",
    "/api/system/workers",
    "/api/workers",
)

FORBIDDEN_PATH_PARTS = (
    "/budget/usage-report",
    "/budgets/usage-report",
)


def _create_app():
    venv_python = BACKEND_ROOT / ".venv" / "bin" / "python"
    if venv_python.exists() and Path(sys.prefix).resolve() != (BACKEND_ROOT / ".venv").resolve():
        os.execv(str(venv_python), [str(venv_python), *sys.argv])
    sys.path.insert(0, str(BACKEND_ROOT))
    cwd = Path.cwd()
    try:
        os.chdir(BACKEND_ROOT)
        from app.main import create_app

        return create_app()
    finally:
        os.chdir(cwd)


def build_snapshot() -> dict[str, Any]:
    snapshot, _duplicate_operation_warnings = build_snapshot_with_warnings()
    return snapshot


def build_snapshot_with_warnings() -> tuple[dict[str, Any], list[str]]:
    app = _create_app()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        spec = app.openapi()
    duplicate_operation_warnings = [
        str(item.message)
        for item in caught
        if "Duplicate Operation ID" in str(item.message)
    ]
    paths = spec.get("paths", {})
    snapshot_paths: dict[str, list[str]] = {}
    for path in sorted(paths):
        methods = paths[path]
        if not isinstance(methods, dict):
            continue
        snapshot_paths[path] = sorted(method for method, payload in methods.items() if isinstance(payload, dict))
    return (
        {
            "schema_version": 1,
            "source": "core/backend/app/main.py:create_app().openapi()",
            "path_count": len(snapshot_paths),
            "paths": snapshot_paths,
        },
        duplicate_operation_warnings,
    )


def forbidden_paths(paths: set[str]) -> list[str]:
    bad: list[str] = []
    for path in sorted(paths):
        if any(path == prefix or path.startswith(f"{prefix}/") for prefix in FORBIDDEN_PATH_PREFIXES):
            bad.append(path)
            continue
        if "/jobs/" in path and any(part in path for part in FORBIDDEN_PATH_PARTS):
            bad.append(path)
    return bad


def write_snapshot() -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(build_snapshot(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_snapshot() -> list[str]:
    errors: list[str] = []
    current, duplicate_operation_warnings = build_snapshot_with_warnings()
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    if current != expected:
        errors.append("OpenAPI path snapshot is stale; run python tools/update_openapi_snapshot.py --write")
    if duplicate_operation_warnings:
        errors.append(
            "OpenAPI duplicate operation IDs are present: "
            + "; ".join(sorted(set(duplicate_operation_warnings)))
        )
    bad = forbidden_paths(set(current.get("paths", {})))
    if bad:
        errors.append("Forbidden job/worker API paths are present: " + ", ".join(bad))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Update or validate the Core OpenAPI path snapshot.")
    parser.add_argument("--write", action="store_true", help="rewrite the snapshot file")
    parser.add_argument("--check", action="store_true", help="validate the snapshot and forbidden path list")
    args = parser.parse_args()
    if args.write:
        write_snapshot()
        print(f"Wrote {SNAPSHOT_PATH.relative_to(REPO_ROOT)}")
    if args.check or not args.write:
        errors = check_snapshot()
        if errors:
            print("OpenAPI snapshot validation failed.")
            for error in errors:
                print(f"- {error}")
            return 1
        print("OpenAPI snapshot validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
