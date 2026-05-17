from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.addons.install_sessions import InstallSessionsStore
from app.addons.registry import AddonRegistry
from .admin import require_admin_token


class InstallStartRequest(BaseModel):
    addon_id: str = Field(..., min_length=1)


class DeploymentSelectRequest(BaseModel):
    mode: str = Field(..., min_length=1)


class InstallConfigureRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


def build_addons_install_router(registry: AddonRegistry, sessions: InstallSessionsStore) -> APIRouter:
    router = APIRouter()

    @router.post("/addons/install/start")
    def install_start(
        body: InstallStartRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ):
        require_admin_token(x_admin_token, request)
        try:
            session = sessions.start(body.addon_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True, "session": session.to_dict()}

    @router.post("/addons/install/{session_id}/permissions/approve")
    def install_permissions_approve(
        session_id: str,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ):
        require_admin_token(x_admin_token, request)
        try:
            session = sessions.approve_permissions(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="session_not_found")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return {"ok": True, "session": session.to_dict()}

    @router.post("/addons/install/{session_id}/deployment/select")
    def install_deployment_select(
        session_id: str,
        body: DeploymentSelectRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ):
        require_admin_token(x_admin_token, request)
        try:
            session = sessions.select_deployment(session_id, body.mode)
        except KeyError:
            raise HTTPException(status_code=404, detail="session_not_found")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return {"ok": True, "session": session.to_dict()}

    @router.post("/addons/install/{session_id}/configure")
    async def install_configure(
        session_id: str,
        body: InstallConfigureRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ):
        require_admin_token(x_admin_token, request)
        try:
            session, result = await sessions.configure(session_id, registry, body.config)
        except KeyError:
            raise HTTPException(status_code=404, detail="session_not_found")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True, "session": session.to_dict(), "result": result}

    @router.post("/addons/install/{session_id}/verify")
    async def install_verify(
        session_id: str,
        request: Request,
        x_admin_token: str | None = Header(default=None),
    ):
        require_admin_token(x_admin_token, request)
        try:
            session, health = await sessions.verify(session_id, registry)
        except KeyError:
            raise HTTPException(status_code=404, detail="session_not_found")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True, "session": session.to_dict(), "health": health}

    @router.get("/addons/install/{session_id}")
    def install_get(session_id: str):
        try:
            session = sessions.get(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="session_not_found")
        return {"ok": True, "session": session.to_dict()}

    return router
