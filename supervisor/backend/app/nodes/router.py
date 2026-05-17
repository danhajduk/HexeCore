from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.admin import require_admin_request

from .models import NodeRecord, NodeRegistryListResponse
from .service import NodesDomainService
from .ui_manifest_service import NodeUiManifestFetchResponse, NodeUiManifestFetchService


def build_nodes_router(
    service: NodesDomainService | None = None,
    manifest_service: NodeUiManifestFetchService | None = None,
) -> APIRouter:
    router = APIRouter(tags=["nodes"])
    nodes = service or NodesDomainService()
    manifests = manifest_service or NodeUiManifestFetchService(nodes)

    @router.get("/nodes")
    def list_nodes() -> NodeRegistryListResponse:
        return NodeRegistryListResponse(items=nodes.list_nodes())

    @router.get("/nodes/{node_id}")
    def get_node(node_id: str) -> dict[str, NodeRecord]:
        return {"node": nodes.get_node(node_id)}

    @router.get("/nodes/{node_id}/ui-manifest")
    async def get_node_ui_manifest(node_id: str, request: Request) -> NodeUiManifestFetchResponse:
        require_admin_request(request)
        return await manifests.fetch_manifest(node_id)

    return router
