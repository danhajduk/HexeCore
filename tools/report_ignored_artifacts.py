#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("core", "supervisor")

SOURCE_OWNED = (
    "backend/app",
    "backend/hexe_supervisor",
    "backend/tests",
    "frontend/src",
    "frontend/public",
    "addons",
    "scripts",
    "shared",
    "systemd",
)


@dataclass(frozen=True)
class ArtifactRule:
    token: str
    category: str
    delete_safe: bool = True


ARTIFACT_RULES = (
    ArtifactRule("node_modules", "frontend dependency cache"),
    ArtifactRule("dist", "frontend build output"),
    ArtifactRule(".vite", "Vite cache"),
    ArtifactRule(".venv", "Python virtual environment"),
    ArtifactRule(".pytest_cache", "pytest cache"),
    ArtifactRule("__pycache__", "Python bytecode cache"),
    ArtifactRule("logs", "runtime logs"),
    ArtifactRule("data", "runtime data"),
    ArtifactRule("runtime", "runtime state"),
    ArtifactRule(".runtime", "runtime state"),
    ArtifactRule("temp", "temporary runtime files"),
    ArtifactRule("var", "runtime state"),
    ArtifactRule(".store_backup", "store backup workspace"),
    ArtifactRule(".store_staging", "store staging workspace"),
    ArtifactRule(".config", "local private operator config", delete_safe=False),
)


@dataclass(frozen=True)
class Artifact:
    path: Path
    category: str
    delete_safe: bool


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _ignored_paths() -> list[Path]:
    result = _run_git(["status", "--ignored", "--short", *SCAN_ROOTS])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status --ignored failed")
    paths: list[Path] = []
    for line in result.stdout.splitlines():
        if not line.startswith("!! "):
            continue
        rel = line[3:].strip().rstrip("/")
        if rel:
            paths.append(Path(rel))
    return paths


def _rule_for(path: Path) -> ArtifactRule | None:
    parts = set(path.parts)
    name = path.name
    for rule in ARTIFACT_RULES:
        if rule.token in parts or rule.token == name:
            return rule
    if name.endswith(".tsbuildinfo"):
        return ArtifactRule("*.tsbuildinfo", "TypeScript build cache")
    return None


def _is_ignored(path: Path) -> bool:
    return _run_git(["check-ignore", "-q", "--", str(path)]).returncode == 0


def _has_tracked_files(path: Path) -> bool:
    result = _run_git(["ls-files", "--", str(path)])
    return bool(result.stdout.strip())


def discover_artifacts() -> list[Artifact]:
    artifacts: list[Artifact] = []
    seen: set[Path] = set()
    for path in _ignored_paths():
        if path in seen:
            continue
        seen.add(path)
        rule = _rule_for(path)
        if rule is None:
            continue
        directly_ignored = _is_ignored(path)
        category = rule.category if directly_ignored else f"{rule.category} container"
        artifacts.append(Artifact(path=path, category=category, delete_safe=rule.delete_safe and directly_ignored))
    return sorted(artifacts, key=lambda item: str(item.path))


def _delete(path: Path) -> None:
    target = REPO_ROOT / path
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink(missing_ok=True)


def report(*, delete: bool) -> int:
    artifacts = discover_artifacts()
    print("Source-owned Core/Supervisor areas:")
    for root in SCAN_ROOTS:
        for owned in SOURCE_OWNED:
            print(f"- {root}/{owned}")
    print()
    if not artifacts:
        print("No ignored Core/Supervisor artifacts matched the cleanup allowlist.")
        return 0

    print("Ignored Core/Supervisor artifacts:")
    for artifact in artifacts:
        action = "report-only"
        if delete:
            if not artifact.delete_safe:
                action = "kept-report-only"
            elif _has_tracked_files(artifact.path):
                action = "kept-has-tracked-files"
            else:
                _delete(artifact.path)
                action = "deleted"
        print(f"- {artifact.path} [{artifact.category}] {action}")

    if not delete:
        print()
        print("No files were deleted. Re-run with --delete to remove delete-safe artifacts.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Report ignored local artifacts under Core and Supervisor.")
    parser.add_argument("--delete", action="store_true", help="delete allowlisted ignored artifacts after reporting them")
    args = parser.parse_args()
    return report(delete=args.delete)


if __name__ == "__main__":
    raise SystemExit(main())
