from fastapi import APIRouter

from .service import AssistantAssertionService


def build_assistant_auth_router(service: AssistantAssertionService) -> APIRouter:
    router = APIRouter(tags=["assistant-authorization"])

    @router.get("/.well-known/hexe-core-jwks.json")
    async def assistant_jwks() -> dict:
        return await service.keys.jwks()

    return router
