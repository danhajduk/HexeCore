from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


NODE_UI_MANIFEST_SCHEMA_VERSION = "1.0"

_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")
_ENDPOINT_RE = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*(?:\{[A-Za-z0-9_:-]{1,64}\}[A-Za-z0-9._~!$&'()*+,;=:@%/-]*)*$")
_UNSAFE_TEXT_RE = re.compile(
    r"(<\s*/?\s*(script|iframe|object|embed|style|link|meta|html|body)\b|javascript:|data:text/html|on[a-z]+\s*=)",
    re.IGNORECASE,
)


class NodeUiManifestValidationError(ValueError):
    pass


class NodeUiRefreshMode(str, Enum):
    LIVE = "live"
    NEAR_LIVE = "near_live"
    MANUAL = "manual"
    DETAIL = "detail"
    STATIC = "static"


class NodeUiActionMethod(str, Enum):
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class NodeUiConfirmationTone(str, Enum):
    INFO = "info"
    WARNING = "warning"
    DANGER = "danger"


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if _UNSAFE_TEXT_RE.search(cleaned):
        raise ValueError("unsafe_executable_text")
    return cleaned


def _validate_id(value: str) -> str:
    cleaned = _clean_text(value)
    if cleaned is None or not _ID_RE.fullmatch(cleaned):
        raise ValueError("invalid_id")
    return cleaned


def _validate_endpoint(value: str) -> str:
    cleaned = _clean_text(value)
    if cleaned is None or not _ENDPOINT_RE.fullmatch(cleaned):
        raise ValueError("invalid_endpoint")
    return cleaned


def _validate_schema_fragment(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("schema_fragment_must_be_object")
    forbidden = {"component", "react_component", "jsx", "html", "script", "template", "render", "code"}
    if any(str(key).strip().lower() in forbidden for key in value.keys()):
        raise ValueError("executable_schema_fragment_forbidden")
    return dict(value)


class NodeUiRefreshPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: NodeUiRefreshMode
    interval_ms: int | None = Field(default=None, ge=1000, le=300000)
    cache_ttl_ms: int | None = Field(default=None, ge=0, le=3600000)

    @model_validator(mode="after")
    def _validate_interval_for_mode(self) -> "NodeUiRefreshPolicy":
        if self.mode in {NodeUiRefreshMode.LIVE, NodeUiRefreshMode.NEAR_LIVE} and self.interval_ms is None:
            raise ValueError("interval_ms_required_for_polling_refresh")
        if self.mode == NodeUiRefreshMode.LIVE and not (1000 <= int(self.interval_ms or 0) <= 5000):
            raise ValueError("live_interval_must_be_1000_to_5000_ms")
        if self.mode == NodeUiRefreshMode.NEAR_LIVE and not (10000 <= int(self.interval_ms or 0) <= 30000):
            raise ValueError("near_live_interval_must_be_10000_to_30000_ms")
        if self.mode in {NodeUiRefreshMode.MANUAL, NodeUiRefreshMode.DETAIL, NodeUiRefreshMode.STATIC} and self.interval_ms is not None:
            raise ValueError("interval_ms_only_allowed_for_polling_refresh")
        return self


class NodeUiActionConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required: bool = False
    title: str | None = None
    message: str | None = None
    tone: NodeUiConfirmationTone = NodeUiConfirmationTone.WARNING

    @field_validator("title", "message")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        return _clean_text(value)

    @model_validator(mode="after")
    def _validate_required_copy(self) -> "NodeUiActionConfirmation":
        if self.required and not (self.title or self.message):
            raise ValueError("confirmation_copy_required")
        return self


class NodeUiAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    method: NodeUiActionMethod
    endpoint: str
    description: str | None = None
    request_schema: dict[str, Any] = Field(default_factory=dict)
    destructive: bool = False
    sensitive: bool = False
    confirmation: NodeUiActionConfirmation | None = None

    @field_validator("id")
    @classmethod
    def _validate_id_field(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("label", "description")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        return _clean_text(value)

    @field_validator("endpoint")
    @classmethod
    def _validate_endpoint_field(cls, value: str) -> str:
        return _validate_endpoint(value)

    @field_validator("request_schema", mode="before")
    @classmethod
    def _validate_request_schema(cls, value: Any) -> dict[str, Any]:
        return _validate_schema_fragment(value)

    @model_validator(mode="after")
    def _validate_confirmation(self) -> "NodeUiAction":
        if (self.destructive or self.sensitive) and not (self.confirmation and self.confirmation.required):
            raise ValueError("confirmation_required_for_sensitive_or_destructive_action")
        return self


class NodeUiSurface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    title: str
    data_endpoint: str
    description: str | None = None
    detail_endpoint_template: str | None = None
    actions: list[NodeUiAction] = Field(default_factory=list)
    refresh: NodeUiRefreshPolicy

    @field_validator("id", "kind")
    @classmethod
    def _validate_ids(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("title", "description")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        return _clean_text(value)

    @field_validator("data_endpoint", "detail_endpoint_template")
    @classmethod
    def _validate_endpoint_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_endpoint(value)


class NodeUiPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str | None = None
    surfaces: list[NodeUiSurface] = Field(default_factory=list, min_length=1)

    @field_validator("id")
    @classmethod
    def _validate_id_field(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("title", "description")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        return _clean_text(value)


class NodeUiManifest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$id": "https://hexe.local/schemas/node_ui_manifest.schema.json",
            "description": "Core-owned contract for declarative node UI manifests served by nodes at GET /api/node/ui-manifest.",
        },
    )

    schema_version: Literal["1.0"] = Field(...)
    manifest_revision: str | None = None
    node_id: str
    node_type: str
    display_name: str
    pages: list[NodeUiPage] = Field(..., min_length=1)

    @field_validator("manifest_revision", "node_id", "node_type")
    @classmethod
    def _validate_ids(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_id(value)

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if cleaned is None:
            raise ValueError("display_name_required")
        return cleaned

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> "NodeUiManifest":
        page_ids: set[str] = set()
        surface_ids: set[str] = set()
        action_ids: set[tuple[str, str]] = set()
        for page in self.pages:
            if page.id in page_ids:
                raise ValueError("duplicate_page_id")
            page_ids.add(page.id)
            for surface in page.surfaces:
                if surface.id in surface_ids:
                    raise ValueError("duplicate_surface_id")
                surface_ids.add(surface.id)
                for action in surface.actions:
                    key = (surface.id, action.id)
                    if key in action_ids:
                        raise ValueError("duplicate_action_id")
                    action_ids.add(key)
        return self

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def validate_node_ui_manifest(payload: dict[str, Any]) -> NodeUiManifest:
    try:
        return NodeUiManifest.model_validate(payload)
    except ValidationError as exc:
        raise NodeUiManifestValidationError(str(exc)) from exc
