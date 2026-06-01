from __future__ import annotations

import os
from collections.abc import MutableMapping


LEGACY_ENV_PREFIX = "SYNTHIA_"
PRIMARY_ENV_PREFIX = "HEXE_"


def legacy_env_name(name: str) -> str | None:
    if not name.startswith(PRIMARY_ENV_PREFIX):
        return None
    return f"{LEGACY_ENV_PREFIX}{name[len(PRIMARY_ENV_PREFIX):]}"


def getenv(name: str, default: str | None = None, *, blank_is_missing: bool = False) -> str | None:
    value = os.environ.get(name)
    if value is not None and (value or not blank_is_missing):
        return value
    legacy_name = legacy_env_name(name)
    if legacy_name:
        legacy_value = os.environ.get(legacy_name)
        if legacy_value is not None and (legacy_value or not blank_is_missing):
            return legacy_value
    return default


def install_legacy_env_aliases(environ: MutableMapping[str, str] | None = None) -> None:
    target = environ if environ is not None else os.environ
    for key, value in list(target.items()):
        if not key.startswith(LEGACY_ENV_PREFIX):
            continue
        primary_key = f"{PRIMARY_ENV_PREFIX}{key[len(LEGACY_ENV_PREFIX):]}"
        if primary_key not in target:
            target[primary_key] = value
