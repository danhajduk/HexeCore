from __future__ import annotations

import os
import time

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
        self._runtime_refresh_interval_s = self._read_runtime_refresh_interval()
        self._last_runtime_refresh_at = 0.0
        self._registry = NodeRegistry(
            registrations_store=registrations_store or NodeRegistrationsStore(),
            node_governance_status_service=node_governance_status_service,
            runtime_store=runtime_store,
        )

    @staticmethod
    def _read_runtime_refresh_interval() -> float:
        raw = str(os.getenv("SYNTHIA_NODE_RUNTIME_REFRESH_INTERVAL_SECONDS", "5")).strip()
        try:
            return max(0.0, float(raw))
        except Exception:
            return 5.0

    def _refresh_runtime_store(self) -> None:
        if self._runtime_client is None or self._runtime_store is None:
            return
        now = time.monotonic()
        if self._runtime_refresh_interval_s > 0 and now - self._last_runtime_refresh_at < self._runtime_refresh_interval_s:
            return
        try:
            if self._runtime_client.refresh_runtime_store(self._runtime_store):
                self._last_runtime_refresh_at = now
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
