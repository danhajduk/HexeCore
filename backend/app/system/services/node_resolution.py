from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from app.nodes.models_resolution import (
    NodeEffectiveBudgetView,
    TaskExecutionResolutionCandidate,
    TaskExecutionResolutionRequest,
    TaskExecutionResolutionResponse,
)


def _clean_text(value: Any, *, lower: bool = False) -> str:
    cleaned = str(value or "").strip()
    return cleaned.lower() if lower else cleaned


def _normalize_url_for_match(value: Any) -> str:
    raw = _clean_text(value)
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw.rstrip("/").lower()
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


class NodeServiceResolutionService:
    def __init__(self, catalog_store, *, node_registrations_store=None, model_routing_registry_service=None) -> None:
        self._catalog_store = catalog_store
        self._node_registrations_store = node_registrations_store
        self._model_routing_registry_service = model_routing_registry_service

    def _resolve_provider_node_id(
        self,
        *,
        service_item: dict[str, Any],
        provider: str,
        preferred_model: str,
        allowed_models: list[str],
    ) -> str | None:
        explicit_node_id = _clean_text(
            service_item.get("node_id")
            or ((service_item.get("addon_registry") or {}).get("node_id") if isinstance(service_item.get("addon_registry"), dict) else None)
            or ((service_item.get("declared_capacity") or {}).get("node_id") if isinstance(service_item.get("declared_capacity"), dict) else None)
            or ((service_item.get("service_capacity") or {}).get("node_id") if isinstance(service_item.get("service_capacity"), dict) else None)
        )
        if explicit_node_id:
            return explicit_node_id

        endpoint_candidates = {
            _normalize_url_for_match(service_item.get("endpoint")),
            _normalize_url_for_match(service_item.get("base_url")),
        }
        endpoint_candidates = {item for item in endpoint_candidates if item}

        if self._model_routing_registry_service is not None and provider:
            model_candidates = [preferred_model] if preferred_model else []
            model_candidates.extend([item for item in allowed_models if item and item not in model_candidates])
            registry_matches: list[str] = []
            for model_id in model_candidates:
                for item in self._model_routing_registry_service.list(provider=provider):
                    if not bool(getattr(item, "node_available", True)):
                        continue
                    normalized_model_id = _clean_text(getattr(item, "normalized_model_id", ""), lower=True)
                    raw_model_id = _clean_text(getattr(item, "model_id", ""), lower=True)
                    if model_id and model_id not in {normalized_model_id, raw_model_id}:
                        continue
                    registry_matches.append(_clean_text(getattr(item, "node_id", "")))
            unique_registry_matches = sorted({item for item in registry_matches if item})
            if len(unique_registry_matches) == 1:
                return unique_registry_matches[0]

            if endpoint_candidates and self._node_registrations_store is not None:
                for registration in self._node_registrations_store.list():
                    node_api_base = _normalize_url_for_match(getattr(registration, "api_base_url", None))
                    requested_api_base = _normalize_url_for_match(getattr(registration, "requested_api_base_url", None))
                    if node_api_base in endpoint_candidates or requested_api_base in endpoint_candidates:
                        if registration.node_id in unique_registry_matches:
                            return registration.node_id

            if not model_candidates:
                provider_nodes = sorted(
                    {
                        _clean_text(getattr(item, "node_id", ""))
                        for item in self._model_routing_registry_service.list(provider=provider)
                        if bool(getattr(item, "node_available", True))
                    }
                )
                provider_nodes = [item for item in provider_nodes if item]
                if len(provider_nodes) == 1:
                    return provider_nodes[0]

        if endpoint_candidates and self._node_registrations_store is not None:
            for registration in self._node_registrations_store.list():
                node_api_base = _normalize_url_for_match(getattr(registration, "api_base_url", None))
                requested_api_base = _normalize_url_for_match(getattr(registration, "requested_api_base_url", None))
                if node_api_base in endpoint_candidates or requested_api_base in endpoint_candidates:
                    return registration.node_id
        return None

    async def resolve_for_node(
        self,
        *,
        request: TaskExecutionResolutionRequest,
        governance_bundle: dict[str, Any],
        budget_service,
    ) -> TaskExecutionResolutionResponse:
        task_family = _clean_text(request.task_family, lower=True)
        preferred_provider = _clean_text(request.preferred_provider, lower=True)
        preferred_model = _clean_text(request.preferred_model, lower=True)
        routing = (
            governance_bundle.get("routing_policy_constraints")
            if isinstance(governance_bundle.get("routing_policy_constraints"), dict)
            else {}
        )
        allowed_task_families = {
            _clean_text(item, lower=True)
            for item in list(routing.get("allowed_task_families") or [])
            if _clean_text(item, lower=True)
        }
        if allowed_task_families and task_family not in allowed_task_families:
            return TaskExecutionResolutionResponse(
                node_id=request.node_id,
                task_family=task_family,
                task_context=dict(request.task_context or {}),
                selected_service_id=None,
                candidates=[],
            )

        allowed_providers = {
            _clean_text(item, lower=True)
            for item in list(routing.get("allowed_providers") or [])
            if _clean_text(item, lower=True)
        }
        allowed_models_map = {
            _clean_text(provider, lower=True): [
                _clean_text(model, lower=True)
                for model in list(models or [])
                if _clean_text(model, lower=True)
            ]
            for provider, models in dict(routing.get("allowed_models") or {}).items()
            if _clean_text(provider, lower=True)
        }

        catalogs = await self._catalog_store.all_catalogs()
        candidates: list[TaskExecutionResolutionCandidate] = []
        for service_key in sorted(catalogs.keys()):
            item = catalogs.get(service_key)
            if not isinstance(item, dict):
                continue
            capabilities = [
                _clean_text(capability, lower=True)
                for capability in list(item.get("capabilities") or [])
                if _clean_text(capability, lower=True)
            ]
            if task_family not in capabilities:
                continue
            health_status = _clean_text(item.get("health_status") or item.get("health"), lower=True) or "unknown"
            if health_status not in {"ok", "healthy", "unknown"}:
                continue
            provider = _clean_text(item.get("provider"), lower=True)
            if preferred_provider and provider and provider != preferred_provider:
                continue
            if allowed_providers and provider and provider not in allowed_providers:
                continue

            catalog_models = [
                _clean_text(model.get("model_id") if isinstance(model, dict) else model, lower=True)
                for model in list(item.get("models") or [])
                if _clean_text(model.get("model_id") if isinstance(model, dict) else model, lower=True)
            ]
            allowed_models = catalog_models
            if provider and provider in allowed_models_map:
                provider_allowed = allowed_models_map.get(provider) or []
                if provider_allowed:
                    allowed_models = [model for model in catalog_models if model in provider_allowed]
            if preferred_model:
                if allowed_models:
                    allowed_models = [model for model in allowed_models if model == preferred_model]
                elif preferred_model:
                    allowed_models = [preferred_model]
            if preferred_model and not allowed_models:
                continue

            provider_node_id = self._resolve_provider_node_id(
                service_item=item,
                provider=provider,
                preferred_model=preferred_model,
                allowed_models=allowed_models,
            )
            budget_view_payload = budget_service.effective_budget_view(
                node_id=provider_node_id or request.node_id,
                task_family=task_family,
                provider=provider or None,
                model_id=preferred_model or None,
            )
            budget_view = NodeEffectiveBudgetView.model_validate(budget_view_payload)
            if budget_view.status in {"no_matching_grant", "not_configured", "revoked", "expired"}:
                continue

            auth_modes = [str(v).strip() for v in list(item.get("auth_modes") or []) if str(v).strip()]
            auth_mode = _clean_text(item.get("auth_mode")) or (auth_modes[0] if auth_modes else "service_token")
            required_scopes = [str(v).strip() for v in list(item.get("required_scopes") or []) if str(v).strip()]
            if not required_scopes:
                required_scopes = [f"service.execute:{task_family}"]

            declared_capacity = item.get("declared_capacity")
            if not isinstance(declared_capacity, dict):
                declared_capacity = item.get("service_capacity") if isinstance(item.get("service_capacity"), dict) else {}

            candidate = TaskExecutionResolutionCandidate(
                service_id=_clean_text(item.get("service_id") or item.get("service") or service_key),
                provider_node_id=provider_node_id or None,
                service_type=_clean_text(item.get("service_type") or item.get("service")),
                provider=provider or None,
                models_allowed=allowed_models,
                required_scopes=required_scopes,
                auth_mode=auth_mode or "service_token",
                grant_id=budget_view.grant_id,
                resolution_mode="catalog_governance_budget",
                health_status=health_status,
                declared_capacity=dict(declared_capacity or {}),
                budget_view=budget_view,
            )
            candidates.append(candidate)

        candidates.sort(
            key=lambda item: (
                0 if item.provider and item.provider == preferred_provider else 1,
                0 if item.budget_view and item.budget_view.admissible else 1,
                0 if str(item.health_status or "").lower() in {"ok", "healthy"} else 1,
                str(item.service_id or ""),
            )
        )
        selected_service_id = candidates[0].service_id if candidates else None
        return TaskExecutionResolutionResponse(
            node_id=request.node_id,
            task_family=task_family,
            task_context=dict(request.task_context or {}),
            selected_service_id=selected_service_id,
            candidates=candidates,
        )
