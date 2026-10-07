from __future__ import annotations

from typing import Any


ASSISTANT_CAPABILITIES = frozenset({"interaction.assistant.turn", "interaction.assistant.intents"})


async def reconcile_assistant_services(
    registration: Any,
    *,
    service_catalog_store: Any = None,
    service_access_grant_store: Any = None,
    core_service_subject: str | None = None,
) -> None:
    node_id = str(getattr(registration, "node_id", "") or "").strip()
    provided = {
        str(value).strip()
        for value in list(getattr(registration, "provided_task_families", []) or [])
        if str(value).strip()
    }
    endpoints = getattr(registration, "capability_endpoints", {}) or {}
    if not node_id:
        return

    if service_catalog_store is not None:
        for capability in ASSISTANT_CAPABILITIES:
            service_id = f"node-service:{node_id}:{capability}"
            endpoint = endpoints.get(capability) if isinstance(endpoints, dict) else None
            if capability not in provided or not isinstance(endpoint, dict):
                await service_catalog_store.delete_catalog(service_id)
                continue
            operations = endpoint.get("operations") if isinstance(endpoint.get("operations"), dict) else {}
            required_scopes = sorted(
                {
                    str(value.get("scope") or "").strip()
                    for value in operations.values()
                    if isinstance(value, dict) and str(value.get("scope") or "").strip()
                }
            )
            provider_ids = list(endpoint.get("provider_ids") or [])
            await service_catalog_store.upsert_service(
                service_type=capability,
                addon_id=node_id,
                service_id=service_id,
                endpoint=str(endpoint.get("url") or getattr(registration, "api_base_url", "") or "").strip(),
                health="healthy",
                capabilities=[capability],
                provider=provider_ids[0] if provider_ids else None,
                auth_modes=["service_token"],
                required_scopes=required_scopes,
                addon_registry={
                    "node_id": node_id,
                    "node_name": getattr(registration, "node_name", None),
                    "node_type": getattr(registration, "node_type", None),
                    "health_path": endpoint.get("health_path"),
                    "contract_version": endpoint.get("contract_version"),
                },
            )

    subject = str(core_service_subject or "").strip()
    if service_access_grant_store is not None and subject and "interaction.assistant.turn" in provided:
        service_access_grant_store.ensure_active(
            subject_node_id=subject,
            audience=f"node-service:{node_id}:interaction.assistant.turn",
            scopes=["assistant.turn.submit", "assistant.turn.resume"],
        )
