from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

LOGGER = logging.getLogger(__name__)


def _load_json(path: Path, *, warnings: list[str]) -> dict[str, Any]:
    if not path.exists():
        warnings.append(f"boot_order_base_missing:{path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"boot_order_base_invalid:{path}:{exc}")
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_yaml(path: Path, *, warnings: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"boot_order_override_invalid:{path}:{exc}")
        return {}
    return payload if isinstance(payload, dict) else {}


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = _deep_merge(base.get(key), value)
        return merged
    return override if override is not None else base


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _clean_boot_order(payload: Any, *, warnings: list[str], prefix: str) -> dict[str, int]:
    if not isinstance(payload, dict):
        warnings.append(f"boot_order_invalid:{prefix}")
        return {}
    cleaned: dict[str, int] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            warnings.append(f"boot_order_key_invalid:{prefix}")
            continue
        parsed = _coerce_int(value)
        if parsed is None:
            warnings.append(f"boot_order_value_invalid:{prefix}:{key}")
            continue
        cleaned[key] = parsed
    return cleaned


def _clean_dependencies(payload: Any, *, warnings: list[str], prefix: str) -> dict[str, list[str]]:
    if not isinstance(payload, dict):
        warnings.append(f"dependencies_invalid:{prefix}")
        return {}
    cleaned: dict[str, list[str]] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            warnings.append(f"dependencies_key_invalid:{prefix}")
            continue
        if value is None:
            cleaned[key] = []
            continue
        if isinstance(value, str):
            cleaned[key] = [value]
            continue
        if isinstance(value, list):
            items = [item for item in value if isinstance(item, str)]
            if len(items) != len(value):
                warnings.append(f"dependencies_items_invalid:{prefix}:{key}")
            cleaned[key] = items
            continue
        warnings.append(f"dependencies_value_invalid:{prefix}:{key}")
    return cleaned


def _clean_section(payload: Any, *, warnings: list[str], section: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        warnings.append(f"section_invalid:{section}")
        return {"boot_order": {}, "dependencies": {}}
    boot_order = _clean_boot_order(payload.get("boot_order", {}), warnings=warnings, prefix=section)
    dependencies = _clean_dependencies(payload.get("dependencies", {}), warnings=warnings, prefix=section)
    cleaned = {"boot_order": boot_order, "dependencies": dependencies}
    for key, value in payload.items():
        if key in cleaned:
            continue
        cleaned[key] = value
    return cleaned


def load_boot_order_plan(
    base_path: str | Path = "var/supervisor/boot-order.json",
    override_path: str | Path = "var/supervisor/boot-order.override.yaml",
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    base = _load_json(Path(base_path), warnings=warnings)
    override = _load_yaml(Path(override_path), warnings=warnings)
    merged = _deep_merge(base, override)
    if not isinstance(merged, dict):
        warnings.append("boot_order_merge_invalid")
        merged = {}
    cleaned = {
        "core": _clean_section(merged.get("core", {}), warnings=warnings, section="core"),
        "nodes": _clean_section(merged.get("nodes", {}), warnings=warnings, section="nodes"),
        "services": _clean_section(merged.get("services", {}), warnings=warnings, section="services"),
    }
    for warning in warnings:
        LOGGER.warning("Supervisor boot-order warning: %s", warning)
    return cleaned, warnings
