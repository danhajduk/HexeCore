#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
import json


REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = REPO_ROOT / "docs" / "core" / "api" / "openapi-paths.snapshot.json"
APPENDIX_PATH = REPO_ROOT / "docs" / "core" / "api" / "generated-openapi-paths.md"


def render_appendix() -> str:
    payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("openapi snapshot missing paths object")
    lines = [
        "# Generated OpenAPI Paths",
        "",
        "Status: Generated",
        "",
        "This file is generated from `openapi-paths.snapshot.json`.",
        "Do not edit path rows by hand; run `python tools/update_api_route_appendix.py --write`.",
        "",
        f"Path count: {len(paths)}",
        "",
        "| Path | Methods |",
        "| --- | --- |",
    ]
    for path in sorted(paths):
        methods = paths[path]
        if not isinstance(methods, list):
            methods = []
        method_text = ", ".join(str(method).upper() for method in methods)
        lines.append(f"| `{path}` | `{method_text}` |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or check the Core OpenAPI path appendix.")
    parser.add_argument("--write", action="store_true", help="write generated appendix")
    parser.add_argument("--check", action="store_true", help="check generated appendix")
    args = parser.parse_args()
    if not args.write and not args.check:
        args.check = True

    expected = render_appendix()
    current = APPENDIX_PATH.read_text(encoding="utf-8") if APPENDIX_PATH.exists() else ""
    if args.write:
        APPENDIX_PATH.write_text(expected, encoding="utf-8")
        print(f"Wrote {APPENDIX_PATH.relative_to(REPO_ROOT)}")
        return 0
    if current != expected:
        print(
            "Generated OpenAPI path appendix is stale; run python tools/update_api_route_appendix.py --write",
            file=sys.stderr,
        )
        return 1
    print("Generated OpenAPI path appendix validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
