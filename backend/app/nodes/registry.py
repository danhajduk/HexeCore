from __future__ import annotations

from app.system.onboarding import NodeGovernanceStatusService, NodeRegistrationsStore, node_registry_payload

from .models import NodeCapabilitySummary, NodeRecord, NodeStatusSummary


def _node_record_from_payload(payload: dict[str, object]) -> NodeRecord:
    return NodeRecord(
        node_id=str(payload.get("node_id") or ""),
        node_name=str(payload.get("node_name") or ""),
        node_type=str(payload.get("node_type") or ""),
        requested_node_type=str(payload.get("requested_node_type") or "").strip() or None,
        node_software_version=str(payload.get("node_software_version") or ""),
        approved_by_user_id=str(payload.get("approved_by_user_id") or "").strip() or None,
        approved_at=str(payload.get("approved_at") or "").strip() or None,
        source_onboarding_session_id=str(payload.get("source_onboarding_session_id") or "").strip() or None,
        created_at=str(payload.get("created_at") or "").strip() or None,
        updated_at=str(payload.get("updated_at") or "").strip() or None,
        provider_intelligence=[
            dict(item) for item in list(payload.get("provider_intelligence") or []) if isinstance(item, dict)
        ],
        capabilities=NodeCapabilitySummary(
            declared_capabilities=[str(v) for v in list(payload.get("declared_capabilities") or []) if str(v).strip()],
            enabled_providers=[str(v) for v in list(payload.get("enabled_providers") or []) if str(v).strip()],
            capability_profile_id=str(payload.get("capability_profile_id") or "").strip() or None,
            capability_status=str(payload.get("capability_status") or "missing"),
            capability_declaration_version=str(payload.get("capability_declaration_version") or "").strip() or None,
            capability_declaration_timestamp=str(payload.get("capability_declaration_timestamp") or "").strip() or None,
        ),
        status=NodeStatusSummary(
            trust_status=str(payload.get("trust_status") or "pending"),
            registry_state=str(payload.get("registry_state") or "pending"),
            governance_sync_status=str(payload.get("governance_sync_status") or "pending"),
            operational_ready=bool(payload.get("operational_ready")),
            active_governance_version=str(payload.get("active_governance_version") or "").strip() or None,
            governance_last_issued_at=str(payload.get("governance_last_issued_at") or "").strip() or None,
            governance_last_refresh_request_at=str(payload.get("governance_last_refresh_request_at") or "").strip() or None,
        ),
    )


class NodeRegistry:
    def __init__(
        self,
        registrations_store: NodeRegistrationsStore | None = None,
        node_governance_status_service: NodeGovernanceStatusService | None = None,
    ) -> None:
        self._registrations_store = registrations_store or NodeRegistrationsStore()
        self._node_governance_status_service = node_governance_status_service

    def list(self) -> list[NodeRecord]:
        return [
            _node_record_from_payload(node_registry_payload(item, self._node_governance_status_service))
            for item in self._registrations_store.list()
        ]

    def get(self, node_id: str) -> NodeRecord | None:
        item = self._registrations_store.get(node_id)
        if item is None:
            return None
        return _node_record_from_payload(node_registry_payload(item, self._node_governance_status_service))
