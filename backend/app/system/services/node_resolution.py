from __future__ import annotations

from typing import Any

from app.nodes.models_resolution import (
    NodeEffectiveBudgetView,
    TaskExecutionResolutionCandidate,
    TaskExecutionResolutionRequest,
    TaskExecutionResolutionResponse,
)


def _clean_text(value: Any, *, lower: bool = False) -> str:
    cleaned = str(value or "").strip()
    return cleaned.lower() if lower else cleaned


class NodeServiceResolutionService:
    def __init__(self, catalog_store) -> None:
        self._catalog_store = catalog_store

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

            budget_view_payload = budget_service.effective_budget_view(
                node_id=request.node_id,
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

