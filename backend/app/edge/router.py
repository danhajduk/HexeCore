from __future__ import annotations

from fastapi import APIRouter, Header, Request

from app.api.admin import require_admin_token

from .models import CloudflareSettings, EdgePublicationCreateRequest, EdgePublicationUpdateRequest
from .service import EdgeGatewayService


def build_edge_router(service: EdgeGatewayService) -> APIRouter:
    router = APIRouter(tags=["edge"])

    @router.get("/edge/status")
    async def edge_status():
        return await service.status()

    @router.get("/edge/publications")
    async def list_publications():
        return {"items": [item.model_dump(mode="json") for item in await service.list_publications()]}

    @router.post("/edge/publications")
    async def create_publication(
        body: EdgePublicationCreateRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ):
        require_admin_token(x_admin_token, request)
        item = await service.create_publication(body)
        return {"ok": True, "publication": item.model_dump(mode="json")}

    @router.patch("/edge/publications/{publication_id}")
    async def update_publication(
        publication_id: str,
        body: EdgePublicationUpdateRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ):
        require_admin_token(x_admin_token, request)
        item = await service.update_publication(publication_id, body)
        return {"ok": True, "publication": item.model_dump(mode="json")}

    @router.delete("/edge/publications/{publication_id}")
    async def delete_publication(
        publication_id: str,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ):
        require_admin_token(x_admin_token, request)
        await service.delete_publication(publication_id)
        return {"ok": True}

    @router.get("/edge/public-identity")
    async def public_identity():
        return await service.public_identity()

    @router.post("/edge/reconcile")
    async def reconcile(
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ):
        require_admin_token(x_admin_token, request)
        return {"ok": True, "reconcile": await service.reconcile()}

    @router.post("/edge/cloudflare/test")
    async def cloudflare_test(
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ):
        require_admin_token(x_admin_token, request)
        return await service.dry_run()

    @router.get("/edge/cloudflare/settings")
    async def get_cloudflare_settings():
        return await service.get_cloudflare_settings()

    @router.put("/edge/cloudflare/settings")
    async def put_cloudflare_settings(
        body: CloudflareSettings,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ):
        require_admin_token(x_admin_token, request)
        return await service.update_cloudflare_settings(body)

    return router
