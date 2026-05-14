from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


JsonScalar: TypeAlias = str | int | float | bool | None
JsonObject: TypeAlias = dict[str, Any]

_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")
_UNSAFE_TEXT_RE = re.compile(
    r"(<\s*/?\s*(script|iframe|object|embed|style|link|meta|html|body)\b|javascript:|data:text/html|on[a-z]+\s*=)",
    re.IGNORECASE,
)
_SECRET_KEY_RE = re.compile(r"(password|passwd|secret|token|api[_-]?key|credential|private[_-]?key|session[_-]?cookie)", re.IGNORECASE)


class NodeUiCardValidationError(ValueError):
    pass


class NodeUiTone(str, Enum):
    NEUTRAL = "neutral"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    DANGER = "danger"


class NodeUiRuntimeState(str, Enum):
    UNKNOWN = "unknown"
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    ERROR = "error"


class NodeUiProviderState(str, Enum):
    UNKNOWN = "unknown"
    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    ERROR = "error"


def _parse_datetime(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("datetime_required")
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


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


def _reject_secret_keys(value: Any, *, path: str = "") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            text_key = str(key)
            if _SECRET_KEY_RE.search(text_key):
                raise ValueError(f"secret_key_forbidden:{path + text_key}")
            _reject_secret_keys(nested, path=f"{path}{text_key}.")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_secret_keys(nested, path=f"{path}{index}.")


def _reject_unsafe_text_values(value: Any) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _reject_unsafe_text_values(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_unsafe_text_values(nested)
    elif isinstance(value, str):
        _clean_text(value)


class NodeUiCardError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    tone: NodeUiTone = NodeUiTone.ERROR
    retryable: bool = False

    @field_validator("code")
    @classmethod
    def _validate_code(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("message")
    @classmethod
    def _validate_message(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if cleaned is None:
            raise ValueError("message_required")
        return cleaned


class NodeUiRetryState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retry_after_ms: int | None = Field(default=None, ge=0, le=3600000)
    action_label: str | None = None

    @field_validator("action_label")
    @classmethod
    def _validate_action_label(cls, value: str | None) -> str | None:
        return _clean_text(value)


class NodeUiCardResponseBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_at: str
    stale: bool = False
    empty: bool = False
    errors: list[NodeUiCardError] = Field(default_factory=list)
    retry: NodeUiRetryState | None = None

    @field_validator("updated_at")
    @classmethod
    def _validate_updated_at(cls, value: str) -> str:
        return _parse_datetime(value)

    @model_validator(mode="after")
    def _validate_payload_safety(self) -> "NodeUiCardResponseBase":
        payload = self.model_dump(mode="json", exclude_none=True)
        _reject_secret_keys(payload)
        _reject_unsafe_text_values(payload)
        return self


class NodeUiFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    value: JsonScalar = None
    unit: str | None = None
    tone: NodeUiTone = NodeUiTone.NEUTRAL
    detail: str | None = None

    @field_validator("id")
    @classmethod
    def _validate_id_field(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("label", "unit", "detail")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        return _clean_text(value)


class NodeOverviewCardResponse(NodeUiCardResponseBase):
    kind: Literal["node_overview"] = "node_overview"
    identity: list[NodeUiFact] = Field(default_factory=list)
    lifecycle: list[NodeUiFact] = Field(default_factory=list)
    trust: list[NodeUiFact] = Field(default_factory=list)
    software: list[NodeUiFact] = Field(default_factory=list)
    core_pairing: list[NodeUiFact] = Field(default_factory=list)


class HealthStripItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_name: str
    current_state: str
    tone: NodeUiTone

    @field_validator("state_name", "current_state")
    @classmethod
    def _validate_text(cls, value: str | None) -> str:
        cleaned = _clean_text(value)
        if value is not None and cleaned is None:
            raise ValueError("text_required")
        if cleaned is None:
            raise ValueError("text_required")
        return cleaned


class HealthStripCardResponse(NodeUiCardResponseBase):
    kind: Literal["health_strip"] = "health_strip"
    items: list[HealthStripItem] = Field(default_factory=list)


class FactsCardResponse(NodeUiCardResponseBase):
    kind: Literal["facts_card"] = "facts_card"
    title: str | None = None
    facts: list[NodeUiFact] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str | None) -> str | None:
        return _clean_text(value)


class NodeUiActionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str | None = None
    enabled: bool = True
    reason: str | None = None
    disabled_reason: str | None = None
    tone: NodeUiTone = NodeUiTone.NEUTRAL

    @field_validator("id")
    @classmethod
    def _validate_id_field(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("label", "reason", "disabled_reason")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        return _clean_text(value)


class WarningItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    message: str | None = None
    tone: NodeUiTone = NodeUiTone.WARNING
    actions: list[NodeUiActionState] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_id_field(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("title", "message")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        cleaned = _clean_text(value)
        if value is not None and cleaned is None:
            raise ValueError("text_required")
        return cleaned


class WarningBannerCardResponse(NodeUiCardResponseBase):
    kind: Literal["warning_banner"] = "warning_banner"
    warnings: list[WarningItem] = Field(default_factory=list)


class ActionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    actions: list[NodeUiActionState] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_id_field(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("label")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if cleaned is None:
            raise ValueError("label_required")
        return cleaned


class ActionPanelCardResponse(NodeUiCardResponseBase):
    kind: Literal["action_panel"] = "action_panel"
    groups: list[ActionGroup] = Field(default_factory=list)


class RecordListColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str

    @field_validator("id")
    @classmethod
    def _validate_id_field(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("label")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if cleaned is None:
            raise ValueError("label_required")
        return cleaned


class RecordListItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str | None = None
    status: str | None = None
    tone: NodeUiTone = NodeUiTone.NEUTRAL
    active: bool = False
    detail_ref: JsonObject = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _validate_id_field(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("name", "status")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        return _clean_text(value)


class RecordListCardResponse(NodeUiCardResponseBase):
    kind: Literal["record_list"] = "record_list"
    summary: JsonObject = Field(default_factory=dict)
    columns: list[RecordListColumn] = Field(default_factory=list)
    records: list[RecordListItem] = Field(default_factory=list)


class RuntimeServiceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    state: str | None = None
    tone: NodeUiTone = NodeUiTone.NEUTRAL
    healthy: bool | None = None
    provider: str | None = None
    model: str | None = None
    resource_usage: JsonObject = Field(default_factory=dict)
    last_error: str | None = None
    restart_supported: bool = False
    restart_target: str | None = None
    runtime_state: NodeUiRuntimeState = NodeUiRuntimeState.UNKNOWN
    health_status: NodeUiTone = NodeUiTone.NEUTRAL
    facts: list[NodeUiFact] = Field(default_factory=list)
    actions: list[NodeUiActionState] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_id_field(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("label")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if cleaned is None:
            raise ValueError("label_required")
        return cleaned

    @field_validator("state", "provider", "model", "last_error", "restart_target")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        return _clean_text(value)


class RuntimeServiceCardResponse(NodeUiCardResponseBase):
    kind: Literal["runtime_service"] = "runtime_service"
    actions: list[NodeUiActionState] = Field(default_factory=list)
    supervisor: JsonObject = Field(default_factory=dict)
    services: list[RuntimeServiceItem] = Field(default_factory=list)


class ProviderStatusSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: list[NodeUiFact] = Field(default_factory=list)
    errors: list[NodeUiCardError] = Field(default_factory=list)
    actions: list[NodeUiActionState] = Field(default_factory=list)


class ProviderStatusItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    provider: str | None = None
    state: NodeUiProviderState = NodeUiProviderState.UNKNOWN
    tone: NodeUiTone = NodeUiTone.NEUTRAL
    facts: list[NodeUiFact] = Field(default_factory=list)
    quotas: list[NodeUiFact] = Field(default_factory=list)
    errors: list[NodeUiCardError] = Field(default_factory=list)
    setup: ProviderStatusSetup | None = None

    @field_validator("id", "provider")
    @classmethod
    def _validate_ids(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_id(value)

    @field_validator("label")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if cleaned is None:
            raise ValueError("label_required")
        return cleaned


class ProviderStatusCardResponse(NodeUiCardResponseBase):
    kind: Literal["provider_status"] = "provider_status"
    providers: list[ProviderStatusItem] = Field(default_factory=list)


NodeUiCardResponse: TypeAlias = (
    NodeOverviewCardResponse
    | HealthStripCardResponse
    | FactsCardResponse
    | WarningBannerCardResponse
    | ActionPanelCardResponse
    | RecordListCardResponse
    | RuntimeServiceCardResponse
    | ProviderStatusCardResponse
)


CARD_RESPONSE_MODELS = [
    NodeOverviewCardResponse,
    HealthStripCardResponse,
    FactsCardResponse,
    WarningBannerCardResponse,
    ActionPanelCardResponse,
    RecordListCardResponse,
    RuntimeServiceCardResponse,
    ProviderStatusCardResponse,
]


def validate_node_ui_card_response(kind: str, payload: dict[str, Any]) -> NodeUiCardResponse:
    models = {str(model.model_fields["kind"].default): model for model in CARD_RESPONSE_MODELS}
    model = models.get(str(kind or "").strip())
    if model is None:
        raise NodeUiCardValidationError("unsupported_card_kind")
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise NodeUiCardValidationError(str(exc)) from exc
