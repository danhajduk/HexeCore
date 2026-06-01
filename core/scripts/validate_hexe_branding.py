#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]

SCAN_PATHS = [
    ROOT / "README.md",
    ROOT / "Agents.lock",
    ROOT / "SkillGraph.md",
    ROOT / "backend" / "app",
    ROOT / "frontend" / "src",
    ROOT / "frontend" / "index.html",
    ROOT / "frontend" / "package.json",
    ROOT / "frontend" / "public" / "styles",
    ROOT / "systemd",
    ROOT / "scripts",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "development-guide.md",
    ROOT / "docs" / "index.md",
    ROOT / "docs" / "overview.md",
    ROOT / "docs" / "architecture.md",
    ROOT / "docs" / "core",
    ROOT / "docs" / "json_schema",
    ROOT / "docs" / "mqtt",
    ROOT / "docs" / "nodes",
    ROOT / "docs" / "standards",
    ROOT / "docs" / "supervisor",
]

SKIP_PATH_PARTS = {
    "backend/var",
    "docs/archive",
    "docs/addons/standalone-archive",
    "docs/migration",
    "docs/reports",
    "docs/standards",
    "docs/temp-ai-node",
}

@dataclass(frozen=True)
class AllowedLegacyReference:
    pattern: re.Pattern[str]
    reason: str
    path_patterns: tuple[re.Pattern[str], ...] = ()

    def matches(self, rel_path: str, line: str) -> bool:
        if not self.pattern.search(line.strip()):
            return False
        if not self.path_patterns:
            return True
        return any(pattern.search(rel_path) for pattern in self.path_patterns)


def path_pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


ALLOWED_LEGACY_REFERENCES = [
    AllowedLegacyReference(
        re.compile(r"\bsynthia_(?:addon|node)s?\b"),
        "Legacy MQTT principal types and addon import namespaces are stable persisted identifiers.",
        (
            path_pattern(r"^backend/app/"),
            path_pattern(r"^docs/json_schema/"),
            path_pattern(r"^docs/mqtt/"),
            path_pattern(r"^docs/nodes/"),
        ),
    ),
    AllowedLegacyReference(
        re.compile(r"\bSYNTHIA_(?:[A-Z0-9_]+)?\b"),
        "Legacy environment variables remain accepted as aliases for HEXE_* configuration.",
        (
            path_pattern(r"^backend/app/core/env\.py$"),
            path_pattern(r"^scripts/.*\.sh$"),
            path_pattern(r"^docs/core/api/auth-and-identity\.md$"),
            path_pattern(r"^docs/supervisor/runtime-and-supervision\.md$"),
        ),
    ),
    AllowedLegacyReference(
        re.compile(r"\bsynthia_admin_session\b"),
        "Legacy admin-session cookies are accepted so existing browser sessions survive the rename.",
        (
            path_pattern(r"^backend/app/api/admin\.py$"),
            path_pattern(r"^docs/core/api/auth-and-identity\.md$"),
        ),
    ),
    AllowedLegacyReference(
        re.compile(r"\bsynthia_(?:api_base|theme)\b"),
        "Legacy browser storage keys are read once and migrated to the Hexe keys.",
        (
            path_pattern(r"^frontend/src/"),
            path_pattern(r"^docs/supervisor/runtime-and-supervision\.md$"),
        ),
    ),
    AllowedLegacyReference(
        re.compile(r"\bsynthia-core\.css\b"),
        "The old stylesheet URL remains as a compatibility shim that imports hexe-core.css.",
        (path_pattern(r"^docs/supervisor/runtime-and-supervision\.md$"),),
    ),
    AllowedLegacyReference(
        re.compile(r"\b(?:DEFAULT_LEGACY_INTERNAL_NAMESPACE|legacy_internal_namespace|legacy_compatibility_note)\b"),
        "Platform identity exposes the previous internal namespace only as compatibility metadata.",
        (
            path_pattern(r"^backend/app/system/platform_identity\.py$"),
            path_pattern(r"^frontend/src/core/branding\.tsx$"),
        ),
    ),
    AllowedLegacyReference(
        re.compile(r"stable technical identifiers still use `synthia`"),
        "Operator-facing compatibility note explains why a few persisted identifiers keep old values.",
        (
            path_pattern(r"^backend/app/system/platform_identity\.py$"),
            path_pattern(r"^frontend/src/core/branding\.tsx$"),
        ),
    ),
    AllowedLegacyReference(
        re.compile(r"\bLEGACY_MQTT_TOPIC_ROOT\b|\b\"synthia\"\b"),
        "Legacy MQTT topic root is normalized to hexe for old integration state.",
        (
            path_pattern(r"^backend/app/system/mqtt/topic_families\.py$"),
            path_pattern(r"^backend/app/system/platform_identity\.py$"),
        ),
    ),
    AllowedLegacyReference(
        re.compile(r"\bSynthia-(?:Addon-Catalog|MQTT)\b"),
        "External repository names remain until those upstream repositories are renamed or replaced.",
        (
            path_pattern(r"^backend/app/store/sources\.py$"),
            path_pattern(r"^docs/standards/"),
        ),
    ),
    AllowedLegacyReference(
        re.compile(r"\bsynthia-(?:workflow|documentation|documentation-audit|architecture-audit)\b"),
        "Local Codex skill directory names are historical tool identifiers, not Hexe product branding.",
        (
            path_pattern(r"^Agents\.lock$"),
            path_pattern(r"^SkillGraph\.md$"),
        ),
    ),
]

NEEDLES = [
    re.compile(r"\bSynthia\b"),
    re.compile(r"\bsynthia\b"),
    re.compile(r"\bSYNTHIA_(?:[A-Z0-9_]+)?\b"),
]


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return any(part in rel for part in SKIP_PATH_PARTS)


def allow_match(rel_path: str, line: str) -> AllowedLegacyReference | None:
    for reference in ALLOWED_LEGACY_REFERENCES:
        if reference.matches(rel_path, line):
            return reference
    return None


def allowed(rel_path: str, line: str) -> bool:
    return allow_match(rel_path, line) is not None


def iter_files(base: Path) -> list[Path]:
    if base.is_file():
        return [base]
    return sorted(path for path in base.rglob("*") if path.is_file())


def main() -> int:
    findings: list[str] = []
    for base in SCAN_PATHS:
        for path in iter_files(base):
            if should_skip(path):
                continue
            if path == Path(__file__).resolve():
                continue
            rel = path.relative_to(ROOT).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if not any(pattern.search(line) for pattern in NEEDLES):
                    continue
                if allowed(rel, line):
                    continue
                findings.append(f"{rel}:{lineno}:{line.strip()}")

    if findings:
        print("Active Hexe branding validation failed.")
        for item in findings:
            print(item)
        return 1

    print("Active Hexe branding validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
