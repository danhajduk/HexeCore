from __future__ import annotations

import re
from typing import Any

_PROVIDER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
_CAPACITY_LIMIT_KEYS = {"max_requests", "max_tokens", "max_cost_cents", "max_bytes", "max_compute_units"}


def _normalize_provider_id(value: str) -> str:
    provider = str(value or "").strip().lower()
    if not _PROVIDER_RE.match(provider):
        raise ValueError("invalid_provider_id")
    return provider


def _normalize_model_id(value: str) -> str:
    model = str(value or "").strip()
    if not model:
        raise ValueError("invalid_model_id")
    return model


def _normalize_float_map(raw: Any, *, error_code: str) -> dict[str, float]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(error_code)
    out: dict[str, float] = {}
    for key, value in raw.items():
        metric = str(key or "").strip().lower()
        if not metric:
            continue
        try:
            amount = float(value)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(error_code) from exc
        if amount < 0:
            raise ValueError(error_code)
        out[metric] = amount
    return out


def _normalize_sla_hints(raw: Any, *, error_code: str) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(error_code)
    out: dict[str, Any] = {}
    for key, value in raw.items():
        hint = str(key or "").strip().lower()
        if not hint:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[hint] = value
            continue
        if isinstance(value, list):
            items: list[Any] = []
            for item in value:
                if isinstance(item, (str, int, float, bool)) or item is None:
                    items.append(item)
            out[hint] = items
            continue
        raise ValueError(error_code)
    return out


def normalize_capacity_descriptor(raw: Any, *, scope: str) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"invalid_{scope}_capacity")
    normalized: dict[str, Any] = {}
    service = str(raw.get("service") or "").strip()
    if service:
        normalized["service"] = service
    period = str(raw.get("period") or "").strip().lower()
    if period:
        normalized["period"] = period
    limits = _normalize_float_map(raw.get("limits"), error_code=f"invalid_{scope}_capacity_limits")
    if limits:
        normalized["limits"] = {
            key: value for key, value in limits.items() if key in _CAPACITY_LIMIT_KEYS or key.startswith("max_")
        }
    concurrency = _normalize_float_map(raw.get("concurrency"), error_code=f"invalid_{scope}_capacity_concurrency")
    if concurrency:
        normalized["concurrency"] = concurrency
    sla_hints = _normalize_sla_hints(raw.get("sla_hints"), error_code=f"invalid_{scope}_sla_hints")
    if sla_hints:
        normalized["sla_hints"] = sla_hints
    return normalized


def normalize_provider_capability_report(
    provider_intelligence: list[dict[str, Any]] | None,
    *,
    node_available: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    providers_raw = list(provider_intelligence or [])
    normalized_by_provider: dict[str, dict[str, dict[str, Any]]] = {}
    descriptors: dict[str, dict[str, Any]] = {}

    for provider_item in providers_raw:
        if not isinstance(provider_item, dict):
            continue
        provider = _normalize_provider_id(str(provider_item.get("provider") or ""))
        models = provider_item.get("available_models")
        if models is None:
            models = []
        if not isinstance(models, list):
            raise ValueError("provider_available_models_must_be_list")
        bucket = normalized_by_provider.setdefault(provider, {})
        for model_item in models:
            if not isinstance(model_item, dict):
                continue
            model_id = _normalize_model_id(str(model_item.get("model_id") or ""))
            normalized_model_id = model_id.strip().lower()
            pricing = _normalize_float_map(model_item.get("pricing"), error_code="invalid_pricing_value")
            latency_metrics = _normalize_float_map(
                model_item.get("latency_metrics"), error_code="invalid_latency_value"
            )
            model_capacity = normalize_capacity_descriptor(model_item.get("capacity"), scope="model")
            model_payload = {
                "model_id": model_id,
                "normalized_model_id": normalized_model_id,
                "descriptor_id": f"{provider}:{normalized_model_id}",
                "availability": ("available" if node_available else "unavailable"),
                "pricing": pricing,
                "latency_metrics": latency_metrics,
            }
            if model_capacity:
                model_payload["capacity"] = model_capacity
            existing = bucket.get(normalized_model_id)
            if isinstance(existing, dict):
                merged = dict(existing)
                merged["model_id"] = model_id
                merged["availability"] = model_payload["availability"]
                merged["pricing"] = {**dict(existing.get("pricing") or {}), **pricing}
                merged["latency_metrics"] = {**dict(existing.get("latency_metrics") or {}), **latency_metrics}
                if model_capacity:
                    merged["capacity"] = model_capacity
                model_payload = merged
            bucket[normalized_model_id] = model_payload
            descriptor = descriptors.setdefault(
                normalized_model_id,
                {
                    "normalized_model_id": normalized_model_id,
                    "model_id": model_id,
                    "providers": [],
                    "provider_count": 0,
                },
            )
            providers = descriptor.setdefault("providers", [])
            if provider not in providers:
                providers.append(provider)

    normalized_providers: list[dict[str, Any]] = []
    for provider in sorted(normalized_by_provider.keys()):
        models = list(normalized_by_provider[provider].values())
        models.sort(key=lambda item: str(item.get("normalized_model_id") or ""))
        provider_item = next(
            (
                item
                for item in providers_raw
                if isinstance(item, dict) and _normalize_provider_id(str(item.get("provider") or "")) == provider
            ),
            None,
        )
        payload = {"provider": provider, "available_models": models}
        provider_capacity = normalize_capacity_descriptor(
            provider_item.get("capacity") if isinstance(provider_item, dict) else None,
            scope="provider",
        )
        if provider_capacity:
            payload["capacity"] = provider_capacity
        normalized_providers.append(payload)

    descriptor_items: list[dict[str, Any]] = []
    for key in sorted(descriptors.keys()):
        item = descriptors[key]
        providers = sorted({str(v) for v in list(item.get("providers") or []) if str(v)})
        item["providers"] = providers
        item["provider_count"] = len(providers)
        descriptor_items.append(item)

    return normalized_providers, descriptor_items
