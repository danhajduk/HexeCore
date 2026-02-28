from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)

PermissionType = Literal[
    "filesystem.read",
    "filesystem.write",
    "network.egress",
    "network.ingress",
    "process.spawn",
    "system.metrics.read",
    "mqtt.publish",
    "mqtt.subscribe",
]


def _validate_semver(value: str, field_name: str) -> str:
    val = value.strip()
    if not SEMVER_RE.fullmatch(val):
        raise ValueError(f"{field_name} must be valid semver")
    return val


class SignatureBlock(BaseModel):
    publisher_id: str = Field(..., min_length=1)
    signature: str = Field(..., min_length=1)


class CompatibilitySpec(BaseModel):
    core_min_version: str = Field(..., min_length=1)
    core_max_version: str | None = Field(default=None)
    dependencies: list[str] = Field(...)
    conflicts: list[str] = Field(...)

    @field_validator("core_min_version")
    @classmethod
    def _validate_min_version(cls, value: str) -> str:
        return _validate_semver(value, "core_min_version")

    @field_validator("core_max_version")
    @classmethod
    def _validate_max_version(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_semver(value, "core_max_version")


class AddonManifest(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    core_min_version: str = Field(..., min_length=1)
    core_max_version: str | None = Field(default=None)
    dependencies: list[str] = Field(...)
    conflicts: list[str] = Field(...)
    publisher_id: str = Field(..., min_length=1)
    permissions: list[PermissionType] = Field(...)

    @field_validator("version", "core_min_version")
    @classmethod
    def _validate_required_semver(cls, value: str, info) -> str:
        return _validate_semver(value, info.field_name)

    @field_validator("core_max_version")
    @classmethod
    def _validate_optional_semver(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_semver(value, "core_max_version")


class ReleaseManifest(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    core_min_version: str = Field(..., min_length=1)
    core_max_version: str | None = Field(default=None)
    dependencies: list[str] = Field(...)
    conflicts: list[str] = Field(...)
    checksum: str = Field(..., min_length=1)
    publisher_id: str = Field(..., min_length=1)
    permissions: list[PermissionType] = Field(...)
    signature: SignatureBlock = Field(...)
    compatibility: CompatibilitySpec = Field(...)

    @field_validator("version", "core_min_version")
    @classmethod
    def _validate_required_semver(cls, value: str, info) -> str:
        return _validate_semver(value, info.field_name)

    @field_validator("core_max_version")
    @classmethod
    def _validate_optional_semver(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_semver(value, "core_max_version")


def build_store_models_router() -> APIRouter:
    router = APIRouter()

    @router.get("/schema")
    async def get_store_schemas():
        return {
            "ok": True,
            "schemas": {
                "AddonManifest": AddonManifest.model_json_schema(),
                "ReleaseManifest": ReleaseManifest.model_json_schema(),
                "CompatibilitySpec": CompatibilitySpec.model_json_schema(),
                "SignatureBlock": SignatureBlock.model_json_schema(),
            },
        }

    return router
