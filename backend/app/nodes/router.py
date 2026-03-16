from __future__ import annotations

from fastapi import APIRouter

from .service import NodesDomainService


def build_nodes_router(service: NodesDomainService | None = None) -> APIRouter:
    router = APIRouter(tags=["nodes"])
    nodes = service or NodesDomainService()

    @router.get("/nodes")
    def list_nodes() -> dict[str, object]:
        return {"items": nodes.list_nodes()}

    @router.get("/nodes/{node_id}")
    def get_node(node_id: str) -> dict[str, object]:
        return {"node": nodes.get_node(node_id)}

    return router
