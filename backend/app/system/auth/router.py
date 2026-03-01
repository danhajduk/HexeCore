from __future__ import annotations

import hmac
import json
import os
import secrets
import time

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.admin import require_admin_token
from .tokens import ServiceTokenKeyStore, sign_hs256


class ServiceTokenIssueRequest(BaseModel):
    sub: str = Field(..., min_length=1)
    aud: str = Field(..., min_length=1)
    scp: list[str] = Field(default_factory=list)
    exp: int = Field(..., description="Unix timestamp when token expires.")
    jti: str | None = None


class ServicePrincipalConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., min_length=1)
    secret: str = Field(..., min_length=1)
    subject: str | None = None
    allowed_audiences: list[str] = Field(default_factory=list)
    allowed_scopes: list[str] = Field(default_factory=list)
    max_ttl_s: int | None = None


def _load_service_principals() -> dict[str, ServicePrincipalConfig]:
    raw = os.getenv("SYNTHIA_SERVICE_PRINCIPALS_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}

    items: list[dict] = []
    if isinstance(parsed, list):
        items = [entry for entry in parsed if isinstance(entry, dict)]
    elif isinstance(parsed, dict):
        for key, value in parsed.items():
            if not isinstance(value, dict):
                continue
            merged = {"id": str(key), **value}
            items.append(merged)

    out: dict[str, ServicePrincipalConfig] = {}
    for item in items:
        try:
            principal = ServicePrincipalConfig.model_validate(item)
            out[principal.id] = principal
        except Exception:
            continue
    return out


def _authorize_service_principal(
    body: ServiceTokenIssueRequest,
    now: int,
    principal_id: str | None,
    principal_secret: str | None,
) -> str:
    principal_key = (principal_id or "").strip()
    principal_secret_value = principal_secret or ""
    if not principal_key or not principal_secret_value:
        raise HTTPException(status_code=401, detail="Unauthorized")

    principals = _load_service_principals()
    principal = principals.get(principal_key)
    if principal is None or not hmac.compare_digest(principal.secret, principal_secret_value):
        raise HTTPException(status_code=401, detail="Unauthorized")

    if principal.subject and body.sub != principal.subject:
        raise HTTPException(status_code=403, detail="service_principal_subject_mismatch")
    if principal.allowed_audiences and body.aud not in principal.allowed_audiences:
        raise HTTPException(status_code=403, detail="service_principal_audience_forbidden")
    if principal.allowed_scopes and not set(body.scp).issubset(set(principal.allowed_scopes)):
        raise HTTPException(status_code=403, detail="service_principal_scope_forbidden")
    if principal.max_ttl_s is not None and (body.exp - now) > int(principal.max_ttl_s):
        raise HTTPException(status_code=400, detail="service_principal_ttl_exceeds_max")
    return principal.id


def build_auth_router(key_store: ServiceTokenKeyStore) -> APIRouter:
    router = APIRouter()

    @router.post("/service-token")
    async def issue_service_token(
        body: ServiceTokenIssueRequest,
        request: Request,
        x_admin_token: str | None = Header(default=None),
        x_service_principal_id: str | None = Header(default=None),
        x_service_principal_secret: str | None = Header(default=None),
    ):
        now = int(time.time())
        if body.exp <= now:
            raise HTTPException(status_code=400, detail="exp_must_be_in_future")

        issued_by_mode = "admin"
        issued_by_id = "admin_token"
        try:
            require_admin_token(x_admin_token, request)
        except HTTPException:
            issued_by_mode = "service_principal"
            issued_by_id = _authorize_service_principal(
                body,
                now,
                principal_id=x_service_principal_id,
                principal_secret=x_service_principal_secret,
            )

        key = await key_store.active_key()
        jti = body.jti or secrets.token_urlsafe(16)
        payload = {
            "sub": body.sub,
            "aud": body.aud,
            "scp": [str(s) for s in body.scp],
            "exp": int(body.exp),
            "jti": jti,
            "iat": now,
        }
        header = {"alg": "HS256", "typ": "JWT", "kid": str(key["kid"])}
        token = sign_hs256(header, payload, secret=str(key["secret"]))
        return {
            "ok": True,
            "token": token,
            "claims": payload,
            "kid": key["kid"],
            "issued_by": {"mode": issued_by_mode, "id": issued_by_id},
        }

    @router.post("/service-token/rotate")
    async def rotate_service_token_key(request: Request, x_admin_token: str | None = Header(default=None)):
        require_admin_token(x_admin_token, request)
        ring = await key_store.rotate()
        return {"ok": True, "keys": [{"kid": k.get("kid"), "active": bool(k.get("active"))} for k in ring]}

    return router
