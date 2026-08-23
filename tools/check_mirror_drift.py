#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class MirrorPair:
    core_path: str
    supervisor_path: str
    label: str


MIRROR_PAIRS: tuple[MirrorPair, ...] = (
    MirrorPair("core/backend", "supervisor/backend", "backend app, runtime, requirements, and tests"),
    MirrorPair("core/frontend", "supervisor/frontend", "frontend source, public assets, and package metadata"),
    MirrorPair("core/scripts", "supervisor/scripts", "operator and development scripts"),
    MirrorPair("core/systemd", "supervisor/systemd", "systemd unit and tmpfiles templates"),
    MirrorPair("core/shared", "supervisor/shared", "shared source assets"),
    MirrorPair("core/addons", "supervisor/addons", "bundled addon source"),
)

ABSENT_TRACKED_PREFIXES: tuple[str, ...] = (
    "core/docs",
    "supervisor/docs",
)

INTENTIONAL_EXCEPTIONS: dict[str, str] = {
    "README.md": "Root README and supervisor/README.md describe different checkout entrypoints.",
    "docs/": "Repository docs are canonical at the root docs/ tree after consolidation.",
    "core/var/ and supervisor/var/": "Live runtime defaults are outside this source mirror guard.",
}


@dataclass
class DriftReport:
    checked_files: int = 0
    missing_supervisor: list[str] | None = None
    missing_core: list[str] | None = None
    changed: list[str] | None = None
    forbidden_tracked: list[str] | None = None

    def __post_init__(self) -> None:
        self.missing_supervisor = [] if self.missing_supervisor is None else self.missing_supervisor
        self.missing_core = [] if self.missing_core is None else self.missing_core
        self.changed = [] if self.changed is None else self.changed
        self.forbidden_tracked = [] if self.forbidden_tracked is None else self.forbidden_tracked

    @property
    def ok(self) -> bool:
        return not (self.missing_supervisor or self.missing_core or self.changed or self.forbidden_tracked)


def _git_ls_files(prefix: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", prefix],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _tracked_relative(prefix: str) -> dict[str, Path]:
    prefix_path = Path(prefix)
    tracked: dict[str, Path] = {}
    for raw_path in _git_ls_files(prefix):
        path = Path(raw_path)
        try:
            rel = path.relative_to(prefix_path).as_posix()
        except ValueError:
            continue
        tracked[rel] = REPO_ROOT / path
    return tracked


def _compare_pair(pair: MirrorPair, report: DriftReport) -> None:
    core_files = _tracked_relative(pair.core_path)
    supervisor_files = _tracked_relative(pair.supervisor_path)
    core_rel = set(core_files)
    supervisor_rel = set(supervisor_files)

    for rel in sorted(core_rel - supervisor_rel):
        report.missing_supervisor.append(f"{pair.label}: {pair.supervisor_path}/{rel}")
    for rel in sorted(supervisor_rel - core_rel):
        report.missing_core.append(f"{pair.label}: {pair.core_path}/{rel}")

    for rel in sorted(core_rel & supervisor_rel):
        report.checked_files += 1
        if core_files[rel].read_bytes() != supervisor_files[rel].read_bytes():
            report.changed.append(f"{pair.label}: {pair.core_path}/{rel} != {pair.supervisor_path}/{rel}")


def check_mirror_drift() -> DriftReport:
    report = DriftReport()
    for pair in MIRROR_PAIRS:
        _compare_pair(pair, report)

    for prefix in ABSENT_TRACKED_PREFIXES:
        tracked = _git_ls_files(prefix)
        if tracked:
            report.forbidden_tracked.extend(tracked)

    return report


def _print_section(title: str, entries: list[str], *, limit: int = 80) -> None:
    if not entries:
        return
    print(f"\n{title}:")
    for entry in entries[:limit]:
        print(f"  - {entry}")
    remaining = len(entries) - limit
    if remaining > 0:
        print(f"  ... {remaining} more")


def main() -> int:
    report = check_mirror_drift()
    if report.ok:
        print(f"Core/Supervisor mirror drift guard passed; checked {report.checked_files} mirrored files.")
        return 0

    print("Core/Supervisor mirror drift detected.")
    _print_section("Missing from Supervisor mirror", report.missing_supervisor)
    _print_section("Missing from Core mirror", report.missing_core)
    _print_section("Changed mirrored files", report.changed)
    _print_section("Tracked docs mirror files are forbidden", report.forbidden_tracked)
    print("\nIntentional mirror exceptions:")
    for path, reason in INTENTIONAL_EXCEPTIONS.items():
        print(f"  - {path}: {reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
