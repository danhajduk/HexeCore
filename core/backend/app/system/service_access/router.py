from __future__ import annotations

import json
import os
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.admin import require_admin_token
from app.system.auth import ServiceTokenError, ServiceTokenKeyStore, sign_hs256, validate_claims, verify_hs256
from app.system.audit import AuditLogStore
from app.system.onboarding import NodeRegistrationsStore, NodeTrustIssuanceService


AI_PRIVILEGED_SCOPES = frozenset(
    {
        "ai.prompts.read",
        "ai.prompts.write",
        "ai.prompts.lifecycle",
        "ai.prompts.review",
        "ai.image_templates.read",
        "ai.image_templates.write",
        "ai.image_templates.lifecycle",
        "ai.image_templates.review",
        "ai.jobs.read",
        "ai.jobs.cancel",
        "ai.artifacts.read",
        "ai.artifacts.ack",
        "ai.services.read",
    }
)
ASSISTANT_PRIVILEGED_SCOPES = frozenset(
    {
        "assistant.turn.submit",
        "assistant.turn.cancel",
        "assistant.turn.resume",
        "assistant.intent.list",
        "assistant.intent.register",
        "assistant.intent.update",
        "assistant.intent.lifecycle",
        "assistant.intent.match",
    }
)
PRIVILEGED_SCOPES = AI_PRIVILEGED_SCOPES | ASSISTANT_PRIVILEGED_SCOPES
SERVICE_TOKEN_ISSUER = "hexe-core"
SERVICE_ACCESS_TOKEN_TTL_SECONDS = 600
INTROSPECTION_RATE_LIMIT = 120
INTROSPECTION_RATE_WINDOW_SECONDS = 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


def _clean_scopes(scopes: list[str]) -> list[str]:
    return sorted({str(scope or "").strip() for scope in scopes if str(scope or "").strip()})


def _validate_expiration(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("expires_at_invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("expires_at_timezone_required")
    if parsed <= _utcnow():
        raise ValueError("expires_at_must_be_future")
    return parsed.astimezone(timezone.utc).isoformat()


@dataclass
class ServiceAccessGrant:
    grant_id: str
    subject_node_id: str
    audience: str
    scopes: list[str]
    status: str
    created_at: str
    updated_at: str
    expires_at: str | None = None
    revoked_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_active(self, *, now: datetime | None = None) -> bool:
        if self.status != "active":
            return False
        if not self.expires_at:
            return True
        try:
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        return expires > (now or _utcnow())


class ServiceAccessGrantStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._grants: dict[str, ServiceAccessGrant] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        for item in payload.get("grants", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            try:
                grant = ServiceAccessGrant(**item)
            except TypeError:
                continue
            self._grants[grant.grant_id] = grant

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "grants": [item.to_dict() for item in sorted(self._grants.values(), key=lambda value: value.grant_id)]}
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def list(self) -> list[ServiceAccessGrant]:
        with self._lock:
            return list(sorted(self._grants.values(), key=lambda value: value.created_at))

    def get(self, grant_id: str) -> ServiceAccessGrant | None:
        with self._lock:
            return self._grants.get(str(grant_id or "").strip())

    def create(self, *, subject_node_id: str, audience: str, scopes: list[str], expires_at: str | None) -> ServiceAccessGrant:
        now = _utcnow_iso()
        grant = ServiceAccessGrant(
            grant_id=f"sag-{secrets.token_urlsafe(16)}",
            subject_node_id=subject_node_id,
            audience=audience,
            scopes=_clean_scopes(scopes),
            status="active",
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        with self._lock:
            self._grants[grant.grant_id] = grant
            self._save()
        return grant

    def update(self, grant_id: str, *, scopes: list[str], expires_at: str | None, status: str) -> ServiceAccessGrant | None:
        with self._lock:
            grant = self._grants.get(str(grant_id or "").strip())
            if grant is None:
                return None
            grant.scopes = _clean_scopes(scopes)
            grant.expires_at = expires_at
            grant.status = status
            grant.updated_at = _utcnow_iso()
            if status == "revoked" and not grant.revoked_at:
                grant.revoked_at = grant.updated_at
            elif status == "active":
                grant.revoked_at = None
            self._save()
            return grant

    def revoke(self, grant_id: str) -> ServiceAccessGrant | None:
        grant = self.get(grant_id)
        if grant is None:
            return None
        return self.update(grant_id, scopes=grant.scopes, expires_at=grant.expires_at, status="revoked")

    def find_authorizing(self, *, subject_node_id: str, audience: str, required_scopes: list[str]) -> ServiceAccessGrant | None:
        needed = set(_clean_scopes(required_scopes))
        for grant in self.list():
            if grant.subject_node_id != subject_node_id or grant.audience != audience or not grant.is_active():
                continue
            if needed.issubset(set(grant.scopes)):
                return grant
        return None

    def ensure_active(
        self,
        *,
        subject_node_id: str,
        audience: str,
        scopes: list[str],
    ) -> ServiceAccessGrant:
        required = _clean_scopes(scopes)
        existing = self.find_authorizing(
            subject_node_id=subject_node_id,
            audience=audience,
            required_scopes=required,
        )
        if existing is not None:
            return existing
        return self.create(
            subject_node_id=subject_node_id,
            audience=audience,
            scopes=required,
            expires_at=None,
        )


class ServiceAccessGrantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_node_id: str = Field(..., min_length=1, max_length=128)
    audience: str = Field(..., min_length=1, max_length=256)
    scopes: list[str] = Field(..., min_length=1)
    expires_at: str | None = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        scopes = _clean_scopes(value)
        unsupported = sorted(set(scopes) - PRIVILEGED_SCOPES)
        if unsupported:
            raise ValueError(f"unsupported_privileged_scopes:{','.join(unsupported)}")
        return scopes

    @field_validator("expires_at")
    @classmethod
    def validate_expiration(cls, value: str | None) -> str | None:
        return _validate_expiration(value)


class ServiceAccessGrantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scopes: list[str] = Field(..., min_length=1)
    expires_at: str | None = None
    status: Literal["active", "revoked"] = "active"

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        return ServiceAccessGrantCreate.validate_scopes(value)

    @field_validator("expires_at")
    @classmethod
    def validate_expiration(cls, value: str | None) -> str | None:
        return _validate_expiration(value)


class ServiceAccessGrantModel(BaseModel):
    grant_id: str
    subject_node_id: str
    audience: str
    scopes: list[str]
    status: Literal["active", "revoked"]
    created_at: str
    updated_at: str
    expires_at: str | None = None
    revoked_at: str | None = None


class ServiceAccessGrantResponse(BaseModel):
    ok: Literal[True] = True
    grant: ServiceAccessGrantModel


class ServiceAccessGrantListResponse(BaseModel):
    ok: Literal[True] = True
    items: list[ServiceAccessGrantModel]


class ServiceAccessAuthorizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(..., min_length=1, max_length=128)
    service_id: str = Field(..., min_length=1, max_length=256)
    requested_scopes: list[str] = Field(..., min_length=1)

    @field_validator("requested_scopes")
    @classmethod
    def validate_requested_scopes(cls, value: list[str]) -> list[str]:
        return ServiceAccessGrantCreate.validate_scopes(value)


class ServiceAccessAuthorizeResponse(BaseModel):
    ok: Literal[True] = True
    token: str
    claims: IntrospectionClaims
    grant_id: str


class ServiceTokenIntrospectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(..., min_length=1, max_length=16384)
    expected_audience: str | None = Field(default=None, min_length=1, max_length=256)
    required_scopes: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("required_scopes")
    @classmethod
    def clean_required_scopes(cls, value: list[str]) -> list[str]:
        return _clean_scopes(value)


class IntrospectionClaims(BaseModel):
    sub: str
    aud: str
    scp: list[str]
    exp: int
    iat: int
    jti: str
    iss: str
    token_use: str
    authorization_id: str
    provider_node_id: str | None = None


class ServiceTokenIntrospectionResponse(BaseModel):
    active: bool
    claims: IntrospectionClaims | None = None
    error_code: str | None = None


class _RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - INTROSPECTION_RATE_WINDOW_SECONDS
        with self._lock:
            bucket = self._windows.setdefault(key, [])
            bucket[:] = [entry for entry in bucket if entry >= cutoff]
            if len(bucket) >= INTROSPECTION_RATE_LIMIT:
                return False
            bucket.append(now)
            return True


def _require_trusted_node(
    *,
    node_id: str,
    node_token: str | None,
    trust: NodeTrustIssuanceService,
    registrations: NodeRegistrationsStore,
) -> None:
    if not str(node_id or "").strip():
        raise HTTPException(status_code=401, detail="node_identity_required")
    if not str(node_token or "").strip():
        raise HTTPException(status_code=401, detail="node_trust_token_required")
    if trust.authenticate_node(node_id, str(node_token)) is None:
        raise HTTPException(status_code=403, detail="untrusted_node")
    registration = registrations.get(node_id)
    if registration is None or str(registration.trust_status or "").strip().lower() != "trusted":
        raise HTTPException(status_code=403, detail="untrusted_node")


def _inactive(error_code: str) -> ServiceTokenIntrospectionResponse:
    return ServiceTokenIntrospectionResponse(active=False, error_code=error_code)


def _validation_error_code(exc: ServiceTokenError) -> str:
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


def build_service_access_router(
    *,
    key_store: ServiceTokenKeyStore,
    grant_store: ServiceAccessGrantStore,
    trust: NodeTrustIssuanceService,
    registrations: NodeRegistrationsStore,
    audit: AuditLogStore | None = None,
) -> APIRouter:
    router = APIRouter(tags=["service-access"])
    limiter = _RateLimiter()

    @router.get("/system/nodes/service-access/grants", response_model=ServiceAccessGrantListResponse)
    def list_grants(request: Request, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        return {"ok": True, "items": [grant.to_dict() for grant in grant_store.list()]}

    @router.post("/system/nodes/service-access/grants", response_model=ServiceAccessGrantResponse)
    async def create_grant(body: ServiceAccessGrantCreate, request: Request, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        grant = grant_store.create(**body.model_dump())
        if audit is not None:
            await audit.record(event_type="service_access_grant_created", actor_role="admin", actor_id="admin", details={"grant_id": grant.grant_id, "subject_node_id": grant.subject_node_id, "audience": grant.audience, "scopes": grant.scopes})
        return {"ok": True, "grant": grant.to_dict()}

    @router.get("/system/nodes/service-access/grants/{grant_id}", response_model=ServiceAccessGrantResponse)
    def get_grant(grant_id: str, request: Request, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        grant = grant_store.get(grant_id)
        if grant is None:
            raise HTTPException(status_code=404, detail="service_access_grant_not_found")
        return {"ok": True, "grant": grant.to_dict()}

    @router.put("/system/nodes/service-access/grants/{grant_id}", response_model=ServiceAccessGrantResponse)
    async def update_grant(grant_id: str, body: ServiceAccessGrantUpdate, request: Request, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        grant = grant_store.update(grant_id, **body.model_dump())
        if grant is None:
            raise HTTPException(status_code=404, detail="service_access_grant_not_found")
        if audit is not None:
            await audit.record(event_type="service_access_grant_updated", actor_role="admin", actor_id="admin", details={"grant_id": grant.grant_id, "status": grant.status, "scopes": grant.scopes})
        return {"ok": True, "grant": grant.to_dict()}

    @router.post("/system/nodes/service-access/grants/{grant_id}/revoke", response_model=ServiceAccessGrantResponse)
    async def revoke_grant(grant_id: str, request: Request, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
        require_admin_token(x_admin_token, request)
        grant = grant_store.revoke(grant_id)
        if grant is None:
            raise HTTPException(status_code=404, detail="service_access_grant_not_found")
        if audit is not None:
            await audit.record(event_type="service_access_grant_revoked", actor_role="admin", actor_id="admin", details={"grant_id": grant.grant_id})
        return {"ok": True, "grant": grant.to_dict()}

    @router.post("/system/nodes/service-access/authorize", response_model=ServiceAccessAuthorizeResponse)
    async def authorize_service_access(body: ServiceAccessAuthorizeRequest, x_node_trust_token: str | None = Header(default=None)) -> dict[str, Any]:
        _require_trusted_node(node_id=body.node_id, node_token=x_node_trust_token, trust=trust, registrations=registrations)
        grant = grant_store.find_authorizing(subject_node_id=body.node_id, audience=body.service_id, required_scopes=body.requested_scopes)
        if grant is None:
            raise HTTPException(status_code=403, detail="service_access_not_authorized")
        now = int(time.time())
        exp = now + SERVICE_ACCESS_TOKEN_TTL_SECONDS
        key = await key_store.active_key()
        claims = {
            "iss": SERVICE_TOKEN_ISSUER,
            "token_use": "node_service_access",
            "authorization_id": grant.grant_id,
            "provider_node_id": body.service_id.split(":", 3)[1] if body.service_id.startswith("node-service:") else None,
            "sub": body.node_id,
            "aud": body.service_id,
            "scp": list(body.requested_scopes),
            "iat": now,
            "exp": exp,
            "jti": f"access-{secrets.token_urlsafe(16)}",
        }
        token = sign_hs256({"alg": "HS256", "typ": "JWT", "kid": str(key["kid"])}, claims, secret=str(key["secret"]))
        await key_store.record_token_expiry(kid=str(key["kid"]), exp=exp)
        if audit is not None:
            await audit.record(event_type="service_access_authorized", actor_role="node", actor_id=body.node_id, details={"grant_id": grant.grant_id, "audience": body.service_id, "scopes": body.requested_scopes, "jti": claims["jti"]})
        return {"ok": True, "token": token, "claims": claims, "grant_id": grant.grant_id}

    @router.post(
        "/system/nodes/services/introspect",
        response_model=ServiceTokenIntrospectionResponse,
        responses={
            401: {"description": "Missing provider node identity or trust token."},
            403: {"description": "Untrusted provider node or provider does not own the token audience."},
            429: {"description": "Trusted-provider introspection rate limit exceeded."},
            503: {"description": "Token validation could not be completed; provider must fail closed."},
        },
    )
    async def introspect_service_token(
        body: ServiceTokenIntrospectionRequest,
        request: Request,
        x_node_id: str | None = Header(default=None),
        x_node_trust_token: str | None = Header(default=None),
    ) -> ServiceTokenIntrospectionResponse:
        provider_node_id = str(x_node_id or "").strip()
        _require_trusted_node(node_id=provider_node_id, node_token=x_node_trust_token, trust=trust, registrations=registrations)
        source_ip = str(request.client.host if request.client else "unknown")
        if not limiter.allow(f"{provider_node_id}:{source_ip}"):
            raise HTTPException(status_code=429, detail="rate_limited")
        try:
            _, payload = verify_hs256(body.token, await key_store.verification_keys())
            audience = str(payload.get("aud") or "").strip()
            if not audience:
                raise ServiceTokenError("claim_aud_invalid")
            claims = validate_claims(
                payload,
                audience=audience,
                expected_issuer=SERVICE_TOKEN_ISSUER,
                allowed_token_uses={"node_service", "node_service_access"},
            )
        except ServiceTokenError as exc:
            return _inactive(_validation_error_code(exc))
        except Exception:
            raise HTTPException(status_code=503, detail="token_validation_unavailable")

        token_provider_node_id = str(claims.provider_node_id or "").strip()
        owns_audience = token_provider_node_id == provider_node_id if token_provider_node_id else claims.aud.startswith(f"node-service:{provider_node_id}:")
        if not owns_audience:
            raise HTTPException(status_code=403, detail="service_token_audience_not_owned")
        if body.expected_audience is not None and claims.aud != body.expected_audience:
            return _inactive("token_audience_mismatch")
        if not set(body.required_scopes).issubset(set(claims.scp)):
            return _inactive("token_scope_insufficient")
        if trust.trusted_node(claims.sub) is None:
            return _inactive("token_subject_untrusted")
        subject_registration = registrations.get(claims.sub)
        if subject_registration is None or str(subject_registration.trust_status or "").strip().lower() != "trusted":
            return _inactive("token_subject_untrusted")
        if claims.token_use == "node_service_access":
            grant = grant_store.get(str(claims.authorization_id or ""))
            if grant is None or not grant.is_active():
                return _inactive("token_authorization_revoked")
            if grant.subject_node_id != claims.sub or grant.audience != claims.aud or not set(claims.scp).issubset(set(grant.scopes)):
                return _inactive("token_authorization_revoked")

        result = ServiceTokenIntrospectionResponse(active=True, claims=IntrospectionClaims.model_validate(claims.to_dict()))
        if audit is not None:
            await audit.record(event_type="service_token_introspected", actor_role="node", actor_id=provider_node_id, details={"subject_node_id": claims.sub, "audience": claims.aud, "jti": claims.jti, "authorization_id": claims.authorization_id, "result": "active"})
        return result

    return router
