#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = [REPO_ROOT / "README.md", REPO_ROOT / "supervisor" / "README.md", REPO_ROOT / "docs"]
HISTORICAL_PARTS = {
    "migration",
    "standalone-archive",
    "temp-ai-node",
}
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
STALE_ABSOLUTE_PREFIXES = (
    "/home/dan/Projects/Hexe/",
    "/home/dan/Projects/HexeAiNode/",
    "/home/dan/Projects/HexeEmail/",
)


@dataclass(frozen=True)
class LinkIssue:
    path: Path
    line: int
    target: str
    reason: str

    def format(self) -> str:
        rel = self.path.relative_to(REPO_ROOT)
        return f"{rel}:{self.line}: {self.reason}: {self.target}"


def _is_historical(path: Path) -> bool:
    try:
        parts = path.relative_to(REPO_ROOT / "docs").parts
    except ValueError:
        return False
    return any(part in HISTORICAL_PARTS for part in parts)


def _iter_markdown(paths: list[Path], *, include_historical: bool) -> list[Path]:
    files: list[Path] = []
    for root in paths:
        if root.is_file() and root.suffix.lower() == ".md":
            files.append(root)
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            if include_historical or not _is_historical(path):
                files.append(path)
    return sorted(set(files))


def _strip_fragment(target: str) -> str:
    if "#" not in target:
        return target
    return target.split("#", 1)[0]


def _is_external(target: str) -> bool:
    parsed = urlsplit(target)
    return bool(parsed.scheme and parsed.scheme not in {"", "file"}) or target.startswith("mailto:")


def _link_path(source: Path, target: str) -> Path | None:
    clean = unquote(_strip_fragment(target).strip("<>"))
    if not clean:
        return None
    if clean.startswith(tuple(STALE_ABSOLUTE_PREFIXES)):
        return Path(clean)
    parsed = urlsplit(clean)
    if parsed.scheme == "file":
        return Path(parsed.path)
    if clean.startswith("/"):
        return Path(clean)
    return (source.parent / clean).resolve()


def check_links(paths: list[Path], *, include_historical: bool) -> list[LinkIssue]:
    issues: list[LinkIssue] = []
    for path in _iter_markdown(paths, include_historical=include_historical):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in LINK_RE.finditer(text):
            target = match.group(1).strip()
            if _is_external(target):
                continue
            line = text.count("\n", 0, match.start()) + 1
            if target.startswith(tuple(STALE_ABSOLUTE_PREFIXES)):
                issues.append(LinkIssue(path, line, target, "stale_absolute_path"))
                continue
            resolved = _link_path(path, target)
            if resolved is None:
                continue
            if not resolved.exists():
                issues.append(LinkIssue(path, line, target, "missing_target"))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check active Markdown file links.")
    parser.add_argument("paths", nargs="*", type=Path, help="Markdown file or directory roots to scan.")
    parser.add_argument(
        "--include-historical",
        action="store_true",
        help="also scan migration/archive/temp documentation",
    )
    args = parser.parse_args()

    paths = [path if path.is_absolute() else (REPO_ROOT / path) for path in (args.paths or DEFAULT_ROOTS)]
    issues = check_links(paths, include_historical=args.include_historical)
    if issues:
        for issue in issues:
            print(issue.format())
        print(f"Markdown link check failed: {len(issues)} issue(s).", file=sys.stderr)
        return 1
    print("Markdown link check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
