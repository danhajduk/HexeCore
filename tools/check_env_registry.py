#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "docs" / "config" / "core-env-registry.json"
DOCS_PATH = REPO_ROOT / "docs" / "config" / "environment.md"

SCAN_ROOTS = (
    "core/backend/app",
    "core/backend/hexe_supervisor",
    "core/scripts",
    "core/systemd",
    "core/frontend/src",
    "core/frontend/index.html",
    "core/frontend/vite.config.ts",
)

SCANNED_PREFIXES = (
    "HEXE_",
    "MQTT_",
    "STORE_",
    "SYNTHIA_",
    "CLOUDFLARE_",
    "PLATFORM_",
)

DYNAMIC_ENV_NAMES = {
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ZONE_ID",
}

ENV_PATTERNS = (
    re.compile(r"(?:os\.getenv|os\.environ\.get|getenv)\(\s*[\"']([A-Z][A-Z0-9_]+)[\"']"),
    re.compile(r"os\.environ\[[\"']([A-Z][A-Z0-9_]+)[\"']\]"),
    re.compile(r"(?:process|import\.meta)\.env\.([A-Z][A-Z0-9_]+)"),
    re.compile(r"\$\{([A-Z][A-Z0-9_]+)(?::[-=?][^}]*)?\}"),
    re.compile(r"(?<![A-Za-z0-9_])\$([A-Z][A-Z0-9_]+)(?![A-Za-z0-9_])"),
)

SENSITIVE_MARKERS = (
    "PASSWORD",
    "SECRET",
    "TOKEN",
    "CREDENTIAL",
    "PRINCIPAL",
    "PRIVATE",
)


def _iter_scan_files() -> list[Path]:
    files: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if root.is_file():
            files.append(root)
        elif root.exists():
            files.extend(path for path in root.rglob("*") if path.is_file())
    return sorted(files)


def scan_env_names() -> set[str]:
    names = set(DYNAMIC_ENV_NAMES)
    for path in _iter_scan_files():
        if any(part in {".venv", "node_modules", "dist", "__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in ENV_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group(1)
                if name.startswith(SCANNED_PREFIXES):
                    names.add(name)
    return names


def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def registry_entries(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = registry.get("variables")
    if not isinstance(entries, list):
        raise ValueError("registry variables must be a list")
    by_name: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("registry entries must be objects")
        name = str(entry.get("name") or "").strip()
        if not name:
            raise ValueError("registry entry missing name")
        if name in by_name:
            raise ValueError(f"duplicate registry entry: {name}")
        by_name[name] = entry
    return by_name


def validate_registry() -> list[str]:
    errors: list[str] = []
    scanned = scan_env_names()
    registry = load_registry()
    entries = registry_entries(registry)
    documented = set(entries)

    missing = sorted(scanned - documented)
    stale = sorted(documented - scanned)
    if missing:
        errors.append("Undocumented env vars: " + ", ".join(missing))
    if stale:
        errors.append("Registry env vars no longer found in active source: " + ", ".join(stale))

    for name, entry in sorted(entries.items()):
        owner = str(entry.get("owner") or "").strip()
        description = str(entry.get("description") or "").strip()
        sensitivity = entry.get("sensitive")
        if not owner:
            errors.append(f"{name}: owner is required")
        if not description:
            errors.append(f"{name}: description is required")
        if not isinstance(sensitivity, bool):
            errors.append(f"{name}: sensitive must be true or false")
        if any(marker in name for marker in SENSITIVE_MARKERS) and sensitivity is not True:
            errors.append(f"{name}: name looks sensitive but sensitive=false")
    return errors


def render_markdown(registry: dict[str, Any]) -> str:
    entries = sorted(registry_entries(registry).values(), key=lambda item: (str(item["owner"]), str(item["name"])))
    lines = [
        "# Core Environment Configuration",
        "",
        "Status: Implemented",
        "",
        "This file is generated from `docs/config/core-env-registry.json`.",
        "Run `python tools/check_env_registry.py --write-docs` after intentional configuration changes.",
        "",
        "Sensitive values are marked in the registry and must not be logged or exposed through public APIs.",
        "",
    ]
    current_owner = None
    for entry in entries:
        owner = str(entry["owner"])
        if owner != current_owner:
            current_owner = owner
            lines.extend([f"## {owner}", ""])
            lines.append("| Name | Default | Sensitive | Description |")
            lines.append("| --- | --- | --- | --- |")
        default = entry.get("default")
        default_text = "`unset`" if default in (None, "") else f"`{default}`"
        sensitive = "yes" if entry.get("sensitive") else "no"
        description = str(entry.get("description") or "").replace("|", "\\|")
        lines.append(f"| `{entry['name']}` | {default_text} | {sensitive} | {description} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and render the Core env registry.")
    parser.add_argument("--write-docs", action="store_true", help="rewrite docs/config/environment.md from the registry")
    parser.add_argument("--check-docs", action="store_true", help="fail if generated docs are stale")
    args = parser.parse_args()

    errors = validate_registry()
    registry = load_registry()
    rendered = render_markdown(registry)
    if args.write_docs:
        DOCS_PATH.parent.mkdir(parents=True, exist_ok=True)
        DOCS_PATH.write_text(rendered, encoding="utf-8")
    if args.check_docs:
        current = DOCS_PATH.read_text(encoding="utf-8") if DOCS_PATH.exists() else ""
        if current != rendered:
            errors.append("docs/config/environment.md is stale; run python tools/check_env_registry.py --write-docs")
    if errors:
        print("Environment registry validation failed.")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Environment registry validation passed; documented {len(registry_entries(registry))} env vars.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
