from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.admin import admin_request_actor, require_admin_request
from app.system.audit import AuditLogStore
from app.system.auth import ServiceTokenError, ServiceTokenKeyStore, sign_hs256, validate_claims, verify_hs256
from app.system.onboarding import NodeRegistrationsStore, NodeTrustIssuanceService
from app.system.users import UsersStore

NODE_MANAGEMENT_PERMISSIONS = frozenset(
    {
        "node.manage.read",
        "node.manage.configuration",
        "node.manage.operations",
        "node.manage.assets",
        "node.manage.credentials",
        "node.manage.lifecycle",
        "node.manage.diagnostics",
    }
)
MANAGEMENT_TOKEN_TTL_SECONDS = 300
MANAGEMENT_TOKEN_ISSUER = "hexe-core"
RATE_LIMIT = 1200
RATE_WINDOW_SECONDS = 60


def _scopes(values: list[str]) -> list[str]:
    return sorted({str(value or "").strip() for value in values if str(value or "").strip()})


@dataclass
class ManagementAuthorization:
    authorization_id: str
    operator_id: str
    operator_role: str
    target_node_id: str
    scopes: list[str]
    issued_at: int
    expires_at: int
    status: str = "active"
    revoked_at: int | None = None

    def active(self, now: int | None = None) -> bool:
        return self.status == "active" and self.expires_at > (now or int(time.time()))


class ManagementAuthorizationStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._items: dict[str, ManagementAuthorization] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        for raw in data.get("authorizations", []) if isinstance(data, dict) else []:
            try:
                item = ManagementAuthorization(**raw)
            except (TypeError, ValueError):
                continue
            self._items[item.authorization_id] = item

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"version": 1, "authorizations": [asdict(x) for x in self._items.values()]}, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def put(self, item: ManagementAuthorization) -> None:
        with self._lock:
            self._items[item.authorization_id] = item
            self._save()

    def get(self, authorization_id: str) -> ManagementAuthorization | None:
        with self._lock:
            return self._items.get(str(authorization_id or "").strip())

    def revoke(self, authorization_id: str) -> ManagementAuthorization | None:
        with self._lock:
            item = self._items.get(str(authorization_id or "").strip())
            if item is None:
                return None
            item.status = "revoked"
            item.revoked_at = int(time.time())
            self._save()
            return item


class ManagementAuthorizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_node_id: str = Field(..., min_length=1, max_length=128)
    required_scopes: list[str] = Field(..., min_length=1, max_length=32)

    @field_validator("required_scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        selected = _scopes(value)
        unsupported = sorted(set(selected) - NODE_MANAGEMENT_PERMISSIONS)
        if unsupported:
            raise ValueError(f"unsupported_management_scope:{','.join(unsupported)}")
        return selected


class ManagementClaims(BaseModel):
    sub: str
    aud: str
    scp: list[str]
    exp: int
    iat: int
    jti: str
    iss: str
    token_use: Literal["node_management"]
    authorization_id: str
    provider_node_id: str


class ManagementAuthorizeResponse(BaseModel):
    ok: Literal[True] = True
    token: str
    claims: ManagementClaims
    authorization_id: str


class ManagementIntrospectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(..., min_length=1, max_length=16384)
    required_scopes: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("required_scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        return ManagementAuthorizeRequest.validate_scopes(value)


class ManagementIntrospectionResponse(BaseModel):
    active: bool
    claims: ManagementClaims | None = None
    error_code: str | None = None


class _Limiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            entries = self._entries.setdefault(key, [])
            entries[:] = [x for x in entries if x >= now - RATE_WINDOW_SECONDS]
            if len(entries) >= RATE_LIMIT:
                return False
            entries.append(now)
            return True


class ManagementAuthorizationService:
    def __init__(self, *, keys: ServiceTokenKeyStore, store: ManagementAuthorizationStore) -> None:
        self.keys = keys
        self.store = store

    async def issue(self, *, operator_id: str, operator_role: str, target_node_id: str, scopes: list[str]) -> tuple[str, dict[str, Any]]:
        now = int(time.time())
        exp = now + MANAGEMENT_TOKEN_TTL_SECONDS
        authorization_id = f"nma-{secrets.token_urlsafe(16)}"
        item = ManagementAuthorization(
            authorization_id=authorization_id,
            operator_id=operator_id,
            operator_role=operator_role,
            target_node_id=target_node_id,
            scopes=_scopes(scopes),
            issued_at=now,
            expires_at=exp,
        )
        self.store.put(item)
        key = await self.keys.active_key()
        claims = {
            "iss": MANAGEMENT_TOKEN_ISSUER,
            "token_use": "node_management",
            "authorization_id": authorization_id,
            "provider_node_id": target_node_id,
            "sub": operator_id,
            "aud": f"node-management:{target_node_id}",
            "scp": item.scopes,
            "iat": now,
            "exp": exp,
            "jti": f"management-{secrets.token_urlsafe(16)}",
        }
        token = sign_hs256({"alg": "HS256", "typ": "JWT", "kid": str(key["kid"])}, claims, str(key["secret"]))
        await self.keys.record_token_expiry(kid=str(key["kid"]), exp=exp)
        return token, claims


def _require_node(node_id: str, token: str | None, trust: NodeTrustIssuanceService, registrations: NodeRegistrationsStore) -> None:
    if not node_id:
        raise HTTPException(status_code=401, detail="node_identity_required")
    if not token:
        raise HTTPException(status_code=401, detail="node_trust_token_required")
    if trust.authenticate_node(node_id, token) is None:
        raise HTTPException(status_code=403, detail="untrusted_node")
    registration = registrations.get(node_id)
    if registration is None or str(registration.trust_status).lower() != "trusted":
        raise HTTPException(status_code=403, detail="untrusted_node")


def _token_error(exc: ServiceTokenError) -> str:
    code = str(exc)
    if code in {"token_format_invalid", "token_decode_failed", "token_alg_unsupported"}:
        return "token_malformed"
    if code == "token_signature_invalid":
        return "token_signature_invalid"
    if code == "token_expired":
        return "token_expired"
    if code == "token_use_invalid":
        return "token_use_invalid"
    return "token_claims_invalid"


def build_management_access_router(
    *, service: ManagementAuthorizationService, trust: NodeTrustIssuanceService,
    registrations: NodeRegistrationsStore, users: UsersStore, audit: AuditLogStore | None = None,
) -> APIRouter:
    router = APIRouter(tags=["node-management-access"])
    limiter = _Limiter()

    @router.post(
        "/system/nodes/management/authorize",
        response_model=ManagementAuthorizeResponse,
        responses={
            401: {"description": "Core operator authentication is required."},
            404: {"description": "The target node is not registered."},
            409: {"description": "The target node is not currently trusted."},
        },
    )
    async def authorize(body: ManagementAuthorizeRequest, request: Request) -> dict[str, Any]:
        require_admin_request(request)
        actor_id, actor_role = admin_request_actor(request)
        registration = registrations.get(body.target_node_id)
        if registration is None:
            raise HTTPException(status_code=404, detail="management_target_node_not_found")
        if str(registration.trust_status).lower() != "trusted" or trust.trusted_node(body.target_node_id) is None:
            raise HTTPException(status_code=409, detail="management_target_node_untrusted")
        token, claims = await service.issue(operator_id=actor_id, operator_role=actor_role, target_node_id=body.target_node_id, scopes=body.required_scopes)
        if audit:
            await audit.record(event_type="node_management_authorized", actor_role=actor_role, actor_id=actor_id, details={"authorization_id": claims["authorization_id"], "target_node_id": body.target_node_id, "scopes": body.required_scopes, "jti": claims["jti"]})
        return {"ok": True, "token": token, "claims": claims, "authorization_id": claims["authorization_id"]}

    @router.post(
        "/system/nodes/management/introspect",
        response_model=ManagementIntrospectionResponse,
        responses={
            401: {"description": "Target node identity or trust credential is missing."},
            403: {"description": "The target node is not currently trusted."},
            429: {"description": "Trusted-node validation rate limit exceeded."},
            503: {"description": "Core validation is unavailable; the node must fail closed."},
        },
    )
    async def introspect(body: ManagementIntrospectionRequest, request: Request, x_node_id: str | None = Header(default=None), x_node_trust_token: str | None = Header(default=None)) -> ManagementIntrospectionResponse:
        node_id = str(x_node_id or "").strip()
        _require_node(node_id, x_node_trust_token, trust, registrations)
        source_ip = request.client.host if request.client else "unknown"
        if not limiter.allow(f"{node_id}:{source_ip}"):
            raise HTTPException(status_code=429, detail="rate_limited")
        try:
            _, payload = verify_hs256(body.token, await service.keys.verification_keys())
            claims = validate_claims(payload, audience=f"node-management:{node_id}", required_scopes=body.required_scopes, expected_issuer=MANAGEMENT_TOKEN_ISSUER, allowed_token_uses={"node_management"})
        except ServiceTokenError as exc:
            code = _token_error(exc)
            if str(exc) == "claim_aud_invalid": code = "management_target_mismatch"
            if str(exc) == "claim_scope_missing": code = "management_scope_insufficient"
            if audit:
                await audit.record(event_type="node_management_introspected", actor_role="node", actor_id=node_id, details={"result": "inactive", "error_code": code})
            return ManagementIntrospectionResponse(active=False, error_code=code)
        except Exception:
            raise HTTPException(status_code=503, detail="management_validation_unavailable")
        item = service.store.get(str(claims.authorization_id or ""))
        if item is None or not item.active() or item.target_node_id != node_id or item.operator_id != claims.sub or not set(claims.scp).issubset(set(item.scopes)):
            if audit:
                await audit.record(event_type="node_management_introspected", actor_role="node", actor_id=node_id, details={"authorization_id": claims.authorization_id, "operator_id": claims.sub, "jti": claims.jti, "result": "inactive", "error_code": "management_authorization_revoked"})
            return ManagementIntrospectionResponse(active=False, error_code="management_authorization_revoked")
        if claims.sub not in {"admin_token", "legacy_admin_session"}:
            user = await users.get_user(claims.sub)
            if user is None or not bool(user.get("enabled")) or str(user.get("role")) not in {"owner", "admin"}:
                if audit:
                    await audit.record(event_type="node_management_introspected", actor_role="node", actor_id=node_id, details={"authorization_id": claims.authorization_id, "operator_id": claims.sub, "jti": claims.jti, "result": "inactive", "error_code": "operator_access_revoked"})
                return ManagementIntrospectionResponse(active=False, error_code="operator_access_revoked")
        result = ManagementIntrospectionResponse(active=True, claims=ManagementClaims.model_validate(claims.to_dict()))
        if audit:
            await audit.record(event_type="node_management_introspected", actor_role="node", actor_id=node_id, details={"authorization_id": claims.authorization_id, "operator_id": claims.sub, "scopes": claims.scp, "jti": claims.jti, "result": "active"})
        return result

    @router.post("/system/nodes/management/authorizations/{authorization_id}/revoke")
    async def revoke(authorization_id: str, request: Request) -> dict[str, Any]:
        require_admin_request(request)
        actor_id, actor_role = admin_request_actor(request)
        item = service.store.revoke(authorization_id)
        if item is None:
            raise HTTPException(status_code=404, detail="management_authorization_not_found")
        if audit:
            await audit.record(event_type="node_management_authorization_revoked", actor_role=actor_role, actor_id=actor_id, details={"authorization_id": authorization_id, "target_node_id": item.target_node_id})
        return {"ok": True, "authorization_id": authorization_id, "status": "revoked"}

    return router
