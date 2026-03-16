from __future__ import annotations

from fastapi import HTTPException

from app.system.onboarding import NodeGovernanceStatusService, NodeRegistrationsStore
from app.system.onboarding.registry_view import node_registry_payload


class NodesDomainService:
    def __init__(
        self,
        registrations_store: NodeRegistrationsStore | None = None,
        node_governance_status_service: NodeGovernanceStatusService | None = None,
    ) -> None:
        self._registrations_store = registrations_store or NodeRegistrationsStore()
        self._node_governance_status_service = node_governance_status_service

    def list_nodes(self) -> list[dict[str, object]]:
        return [
            node_registry_payload(item, self._node_governance_status_service)
            for item in self._registrations_store.list()
        ]

    def get_node(self, node_id: str) -> dict[str, object]:
        item = self._registrations_store.get(node_id)
        if item is None:
            raise HTTPException(status_code=404, detail="node_not_found")
        return node_registry_payload(item, self._node_governance_status_service)
