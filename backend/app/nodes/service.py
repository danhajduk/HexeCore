from __future__ import annotations

from fastapi import HTTPException

from app.system.onboarding import NodeGovernanceStatusService, NodeRegistrationsStore
from app.supervisor.client import SupervisorApiClient
from app.supervisor.runtime_store import SupervisorRuntimeNodesStore

from .models import NodeRecord
from .registry import NodeRegistry


class NodesDomainService:
    def __init__(
        self,
        registrations_store: NodeRegistrationsStore | None = None,
        node_governance_status_service: NodeGovernanceStatusService | None = None,
        runtime_store: SupervisorRuntimeNodesStore | None = None,
        runtime_client: SupervisorApiClient | None = None,
    ) -> None:
        self._runtime_store = runtime_store
        self._runtime_client = runtime_client
        self._registry = NodeRegistry(
            registrations_store=registrations_store or NodeRegistrationsStore(),
            node_governance_status_service=node_governance_status_service,
            runtime_store=runtime_store,
        )

    def _refresh_runtime_store(self) -> None:
        if self._runtime_client is None or self._runtime_store is None:
            return
        try:
            self._runtime_client.refresh_runtime_store(self._runtime_store)
        except Exception:
            return

    def list_nodes(self) -> list[NodeRecord]:
        self._refresh_runtime_store()
        return self._registry.list()

    def get_node(self, node_id: str) -> NodeRecord:
        self._refresh_runtime_store()
        item = self._registry.get(node_id)
        if item is None:
            raise HTTPException(status_code=404, detail="node_not_found")
        return item
