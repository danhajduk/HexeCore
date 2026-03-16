from __future__ import annotations

from fastapi import APIRouter

from .models import NodeRecord, NodeRegistryListResponse
from .service import NodesDomainService


def build_nodes_router(service: NodesDomainService | None = None) -> APIRouter:
    router = APIRouter(tags=["nodes"])
    nodes = service or NodesDomainService()

    @router.get("/nodes")
    def list_nodes() -> NodeRegistryListResponse:
        return NodeRegistryListResponse(items=nodes.list_nodes())

    @router.get("/nodes/{node_id}")
    def get_node(node_id: str) -> dict[str, NodeRecord]:
        return {"node": nodes.get_node(node_id)}

    return router
