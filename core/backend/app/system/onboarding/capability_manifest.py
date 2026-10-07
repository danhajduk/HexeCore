from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

CAPABILITY_DECLARATION_SCHEMA_VERSION = "1.0"
SUPPORTED_CAPABILITY_DECLARATION_VERSIONS = {CAPABILITY_DECLARATION_SCHEMA_VERSION}
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
_TASK_FAMILY_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]{1,127}$")
_ASSISTANT_CAPABILITY_OPERATIONS = {
    "interaction.assistant.turn": {
        "submit": ("POST", "/api/interaction/assistant/v1/turns", "assistant.turn.submit"),
        "cancel": ("POST", "/api/interaction/assistant/v1/turns/{turn_id}/cancel", "assistant.turn.cancel"),
        "resume": ("POST", "/api/interaction/assistant/v1/turns/{turn_id}/approvals", "assistant.turn.resume"),
    },
    "interaction.assistant.intents": {
        "list": ("GET", "/api/interaction/assistant/v1/intents", "assistant.intent.list"),
        "register": ("POST", "/api/interaction/assistant/v1/intents", "assistant.intent.register"),
        "update": ("PUT", "/api/interaction/assistant/v1/intents/{intent_id}", "assistant.intent.update"),
        "lifecycle": (
            "POST",
            "/api/interaction/assistant/v1/intents/{intent_id}/lifecycle",
            "assistant.intent.lifecycle",
        ),
        "match": ("POST", "/api/interaction/assistant/v1/intents/match", "assistant.intent.match"),
    },
}


class CapabilityManifestValidationError(ValueError):
    code = "capability_manifest_invalid"

    def __init__(self, detail: str) -> None:
        super().__init__(f"{self.code}: {detail}")


def _clean_list(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = str(item or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _validate_task_family_values(value: Any, *, field_name: str, required: bool = False) -> list[str]:
    if value is None:
        values: list[str] = []
    elif isinstance(value, list):
        values = _clean_list([str(item) for item in value])
    else:
        raise ValueError(f"{field_name}_must_be_list")
    if required and not values:
        raise ValueError(f"{field_name}_empty")
    for item in values:
        if not _TASK_FAMILY_RE.match(item):
            raise ValueError("invalid_task_family")
    return values


class CapabilityNodeMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=3, max_length=128)
    node_type: str = Field(..., min_length=2, max_length=64)
    node_name: str = Field(..., min_length=1, max_length=128)
    node_software_version: str = Field(..., min_length=1, max_length=64)

    @field_validator("node_id")
    @classmethod
    def _validate_node_id(cls, value: str) -> str:
        v = str(value or "").strip()
        if not v.startswith("node-"):
            raise ValueError("invalid_node_id")
        return v


class CapabilityNodeFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telemetry: bool = False
    governance_refresh: bool = False
    lifecycle_events: bool = False
    provider_failover: bool = False


class CapabilityEnvironmentHints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_target: str | None = Field(default=None, max_length=64)
    acceleration: str | None = Field(default=None, max_length=64)
    network_tier: str | None = Field(default=None, max_length=64)
    region: str | None = Field(default=None, max_length=64)


class CapabilityProviderModelMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(..., min_length=1, max_length=128)
    pricing: dict[str, float] = Field(default_factory=dict)
    latency_metrics: dict[str, float] = Field(default_factory=dict)

    @field_validator("model_id")
    @classmethod
    def _validate_model_id(cls, value: str) -> str:
        model_id = str(value or "").strip()
        if not model_id:
            raise ValueError("invalid_model_id")
        return model_id

    @field_validator("pricing", mode="before")
    @classmethod
    def _validate_pricing(cls, value: Any) -> dict[str, float]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("provider_model_pricing_must_be_object")
        out: dict[str, float] = {}
        for key, raw in value.items():
            metric = str(key or "").strip().lower()
            if not metric:
                raise ValueError("invalid_pricing_metric")
            try:
                amount = float(raw)
            except Exception as exc:
                raise ValueError("invalid_pricing_value") from exc
            if amount < 0:
                raise ValueError("invalid_pricing_value")
            out[metric] = amount
        return out

    @field_validator("latency_metrics", mode="before")
    @classmethod
    def _validate_latency_metrics(cls, value: Any) -> dict[str, float]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("provider_model_latency_metrics_must_be_object")
        out: dict[str, float] = {}
        for key, raw in value.items():
            metric = str(key or "").strip().lower()
            if not metric:
                raise ValueError("invalid_latency_metric")
            try:
                latency = float(raw)
            except Exception as exc:
                raise ValueError("invalid_latency_value") from exc
            if latency < 0:
                raise ValueError("invalid_latency_value")
            out[metric] = latency
        return out


class CapabilityProviderIntelligence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., min_length=1, max_length=128)
    available_models: list[CapabilityProviderModelMetadata] = Field(default_factory=list)

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, value: str) -> str:
        provider = str(value or "").strip().lower()
        if not _ID_RE.match(provider):
            raise ValueError("invalid_provider_id")
        return provider

    @field_validator("available_models", mode="before")
    @classmethod
    def _validate_available_models(cls, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("provider_available_models_must_be_list")
        return value


class CapabilityDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_version: str = Field(..., min_length=1, max_length=16)
    node: CapabilityNodeMetadata
    declared_task_families: list[str] = Field(default_factory=list)
    declared_capabilities: list[str] = Field(default_factory=list)
    provided_task_families: list[str] = Field(default_factory=list)
    requested_task_families: list[str] = Field(default_factory=list)
    capability_endpoints: dict[str, dict[str, Any]] = Field(default_factory=dict)
    supported_providers: list[str] = Field(..., min_length=1)
    enabled_providers: list[str] = Field(default_factory=list)
    node_features: CapabilityNodeFeatures
    environment_hints: CapabilityEnvironmentHints
    provider_intelligence: list[CapabilityProviderIntelligence] = Field(default_factory=list)

    @field_validator("manifest_version")
    @classmethod
    def _validate_manifest_version(cls, value: str) -> str:
        v = str(value or "").strip()
        if v not in SUPPORTED_CAPABILITY_DECLARATION_VERSIONS:
            raise ValueError("unsupported_capability_manifest_version")
        return v

    @field_validator("declared_task_families", mode="before")
    @classmethod
    def _validate_task_families(cls, value: Any) -> list[str]:
        return _validate_task_family_values(value, field_name="declared_task_families")

    @field_validator("declared_capabilities", mode="before")
    @classmethod
    def _validate_declared_capabilities(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("declared_capabilities_must_be_list")
        values = _clean_list([str(item) for item in value])
        for item in values:
            if not _TASK_FAMILY_RE.match(item):
                raise ValueError("invalid_declared_capability")
        return values

    @field_validator("provided_task_families", mode="before")
    @classmethod
    def _validate_provided_task_families(cls, value: Any) -> list[str]:
        return _validate_task_family_values(value, field_name="provided_task_families")

    @field_validator("requested_task_families", mode="before")
    @classmethod
    def _validate_requested_task_families(cls, value: Any) -> list[str]:
        return _validate_task_family_values(value, field_name="requested_task_families")

    @field_validator("capability_endpoints", mode="before")
    @classmethod
    def _validate_capability_endpoints(cls, value: Any) -> dict[str, dict[str, Any]]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("capability_endpoints_must_be_object")
        out: dict[str, dict[str, Any]] = {}
        for raw_key, raw_endpoint in value.items():
            key = str(raw_key or "").strip().lower()
            if not _TASK_FAMILY_RE.match(key):
                raise ValueError("invalid_capability_endpoint_key")
            if not isinstance(raw_endpoint, dict):
                raise ValueError("capability_endpoint_must_be_object")
            out[key] = dict(raw_endpoint)
        return out

    @field_validator("supported_providers", mode="before")
    @classmethod
    def _validate_supported_providers(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("supported_providers_must_be_list")
        values = _clean_list([str(item) for item in value])
        if not values:
            raise ValueError("supported_providers_empty")
        for item in values:
            if not _ID_RE.match(item):
                raise ValueError("invalid_provider_id")
        return values

    @field_validator("enabled_providers", mode="before")
    @classmethod
    def _validate_enabled_providers(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("enabled_providers_must_be_list")
        values = _clean_list([str(item) for item in value])
        for item in values:
            if not _ID_RE.match(item):
                raise ValueError("invalid_provider_id")
        return values

    @model_validator(mode="after")
    def _validate_enabled_subset(self) -> "CapabilityDeclaration":
        provider_families = list(self.provided_task_families or self.declared_task_families or [])
        if self.provided_task_families and self.declared_task_families and self.provided_task_families != self.declared_task_families:
            raise ValueError("provided_task_families_must_match_declared_task_families")
        if self.declared_capabilities and self.declared_capabilities != provider_families:
            raise ValueError("declared_capabilities_must_match_provided_task_families")
        if not provider_families and not self.requested_task_families:
            raise ValueError("capability_declaration_requires_provided_or_requested_task_families")
        self.provided_task_families = provider_families
        self.declared_task_families = provider_families
        self.declared_capabilities = provider_families
        endpoint_keys = set(self.capability_endpoints)
        declared = set(provider_families)
        if endpoint_keys - declared:
            raise ValueError("capability_endpoint_not_declared")
        for capability, required_operations in _ASSISTANT_CAPABILITY_OPERATIONS.items():
            if capability not in declared:
                continue
            endpoint = self.capability_endpoints.get(capability)
            if not isinstance(endpoint, dict):
                raise ValueError("assistant_capability_endpoint_required")
            expected_audience = f"node-service:{self.node.node_id}:{capability}"
            if str(endpoint.get("service_id") or "").strip() != expected_audience:
                raise ValueError("assistant_capability_service_id_invalid")
            if str(endpoint.get("audience") or "").strip() != expected_audience:
                raise ValueError("assistant_capability_audience_invalid")
            if str(endpoint.get("contract_version") or "").strip() != "assistant.v1":
                raise ValueError("assistant_capability_contract_version_invalid")
            if str(endpoint.get("schema_catalog") or "").strip() != "/api/schemas/client-node/v2":
                raise ValueError("assistant_capability_schema_catalog_invalid")
            health_path = str(endpoint.get("health_path") or "").strip()
            if not health_path.startswith("/"):
                raise ValueError("assistant_capability_health_path_invalid")
            operations = endpoint.get("operations")
            if not isinstance(operations, dict):
                raise ValueError("assistant_capability_operations_required")
            for operation, (method, path, scope) in required_operations.items():
                metadata = operations.get(operation)
                if not isinstance(metadata, dict):
                    raise ValueError("assistant_capability_operation_missing")
                if str(metadata.get("method") or "").strip().upper() != method:
                    raise ValueError("assistant_capability_operation_method_invalid")
                if str(metadata.get("path") or "").strip() != path:
                    raise ValueError("assistant_capability_operation_path_invalid")
                if str(metadata.get("scope") or "").strip() != scope:
                    raise ValueError("assistant_capability_operation_scope_invalid")
        supported = set(self.supported_providers)
        for provider in self.enabled_providers:
            if provider not in supported:
                raise ValueError("enabled_provider_not_supported")
        for intel in self.provider_intelligence:
            if intel.provider not in supported:
                raise ValueError("provider_intelligence_not_supported")
        return self


def validate_capability_declaration(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = CapabilityDeclaration.model_validate(payload)
        return parsed.model_dump(mode="python")
    except ValidationError as exc:
        raise CapabilityManifestValidationError(str(exc)) from exc
