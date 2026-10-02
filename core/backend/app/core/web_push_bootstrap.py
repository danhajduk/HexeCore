from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.system.audit import AuditLogStore
from app.system.auth.human import authenticate_human_token
from app.system.auth.tokens import ServiceTokenKeyStore
from app.system.platform_identity import load_platform_identity
from app.system.settings.store import SettingsStore
from app.system.users.store import UsersStore

from .web_push_registration import GATEWAY_CREDENTIAL_REF, REGISTRATION_CONTRACT_VERSION, WebPushRegistrationGrantIssuer


BOOTSTRAP_CONTRACT_VERSION = "hexe.web-push-gateway-bootstrap.v1"
DELIVERY_CONTRACT_VERSION = "hexe.web-push-gateway.v1"
GATEWAY_AUDIENCE = "hexe-notification-gateway"
REQUIRED_DELIVERY_SCOPES = frozenset({"notification.publish", "notification.subscription.delete"})
SAFE_GATEWAY_ERRORS = frozenset({
    "bootstrap_invalid", "bootstrap_expired", "bootstrap_replayed", "wrong_core",
    "core_already_registered", "core_revoked", "credential_invalid",
    "credential_version_invalid", "wrong_scope", "wrong_audience",
})


class OwnerBootstrapRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=256)
    bootstrap_token: str = Field(..., min_length=24, max_length=512)


class GatewayCredential(BaseModel):
    version: str = Field(..., min_length=1, max_length=64)
    secret: str = Field(..., min_length=32, max_length=512)
    created_at: datetime
    scopes: list[Literal["notification.publish", "notification.subscription.delete"]]


class GatewayProvisioningResponse(BaseModel):
    contract_version: Literal["hexe.web-push-gateway-bootstrap.v1"]
    core_id: str = Field(..., min_length=16, max_length=160)
    state: Literal["active"]
    gateway_audience: str = Field(..., min_length=3, max_length=160)
    vapid_public_key: str = Field(..., min_length=16, max_length=512)
    subscription_endpoint: str = Field(..., min_length=12, max_length=2048)
    delivery_endpoint: str = Field(..., min_length=12, max_length=2048)
    lifecycle_endpoint: str = Field(..., min_length=12, max_length=2048)
    registration_contract_version: Literal["hexe.web-push-registration.v1"]
    delivery_contract_version: Literal["hexe.web-push-gateway.v1"]
    registration_key_id: str = Field(..., min_length=16, max_length=256)
    delivery_credential: GatewayCredential


class WebPushGatewayBootstrapService:
    def __init__(
        self,
        settings: SettingsStore,
        issuer: WebPushRegistrationGrantIssuer,
        *,
        bootstrap_url: str,
        credential_ref: str = GATEWAY_CREDENTIAL_REF,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._issuer = issuer
        self._bootstrap_url = self._validate_bootstrap_url(bootstrap_url)
        self._credential_ref = credential_ref
        self._client = client

    @staticmethod
    def _validate_bootstrap_url(value: str) -> str:
        try:
            parsed = httpx.URL(str(value or "").strip())
        except Exception:
            return ""
        if parsed.scheme != "https" or not parsed.host or parsed.userinfo or parsed.query or parsed.fragment:
            return ""
        if not parsed.path.endswith("/v1/cores/bootstrap"):
            return ""
        return str(parsed)

    def _operation_url(self, operation: str) -> str:
        if not self._bootstrap_url:
            return ""
        return self._bootstrap_url[: -len("bootstrap")] + operation

    async def status(self) -> dict:
        record = await self._settings.get_sensitive(self._credential_ref)
        if not isinstance(record, dict):
            return {"configured": False, "state": "unconfigured"}
        return {
            "configured": record.get("state") == "active" and bool(record.get("secret")),
            "state": str(record.get("state") or "unconfigured"),
            "credential_version": record.get("credential_version"),
            "registration_key_id": record.get("registration_key_id"),
            "gateway_audience": record.get("gateway_audience"),
            "allowed_scopes": list(record.get("scopes") or []),
            "updated_at": record.get("updated_at"),
        }

    async def provision(self, *, operation: Literal["bootstrap", "rotate"], bootstrap_token: str, core_id: str, canonical_origin: str) -> dict:
        if not self._bootstrap_url:
            raise HTTPException(status_code=503, detail="notification_gateway_bootstrap_unavailable")
        existing = await self._settings.get_sensitive(self._credential_ref)
        if operation == "bootstrap" and isinstance(existing, dict) and existing.get("state") == "active":
            raise HTTPException(status_code=409, detail="core_already_registered")

        candidate_private: str | None = None
        if operation == "rotate":
            if not isinstance(existing, dict) or existing.get("state") != "active":
                raise HTTPException(status_code=409, detail="notification_gateway_not_registered")
            candidate_private, public_key = self._issuer.generate_signing_key()
        else:
            public_key = await self._issuer.public_key()

        key_id = self._issuer.key_id(core_id)
        request_body = {
            "contract_version": BOOTSTRAP_CONTRACT_VERSION,
            "operation": operation,
            "bootstrap_token": bootstrap_token,
            "core_id": core_id,
            "canonical_origin": canonical_origin,
            "registration_contract_version": REGISTRATION_CONTRACT_VERSION,
            "registration_public_key": public_key,
            "registration_key_id": key_id,
            "registration_key_algorithm": "EdDSA",
        }
        response = await self._post(self._operation_url(operation), request_body)
        if response.status_code not in {200, 201}:
            raise self._gateway_error(response)
        try:
            value = GatewayProvisioningResponse.model_validate(response.json())
        except Exception as exc:
            raise HTTPException(status_code=502, detail="notification_gateway_response_invalid") from exc
        self._validate_response(value, core_id=core_id, key_id=key_id)

        now = datetime.now(timezone.utc).isoformat()
        record = {
            "contract_version": value.contract_version,
            "core_id": core_id,
            "state": "active",
            "gateway_audience": value.gateway_audience,
            "vapid_public_key": value.vapid_public_key,
            "subscription_endpoint": value.subscription_endpoint,
            "delivery_endpoint": value.delivery_endpoint,
            "lifecycle_endpoint": value.lifecycle_endpoint,
            "registration_key_id": value.registration_key_id,
            "registration_public_key": public_key,
            "credential_version": value.delivery_credential.version,
            "credential_created_at": value.delivery_credential.created_at.isoformat(),
            "scopes": sorted(value.delivery_credential.scopes),
            "secret": value.delivery_credential.secret,
            "updated_at": now,
        }
        if candidate_private is not None:
            await self._issuer.install_signing_key(candidate_private)
        await self._settings.set_sensitive(self._credential_ref, record)
        return await self.status()

    async def revoke(self, *, bootstrap_token: str, core_id: str, canonical_origin: str) -> dict:
        existing = await self._settings.get_sensitive(self._credential_ref)
        if not isinstance(existing, dict) or existing.get("state") != "active":
            raise HTTPException(status_code=409, detail="notification_gateway_not_registered")
        body = {
            "contract_version": BOOTSTRAP_CONTRACT_VERSION,
            "operation": "revoke",
            "bootstrap_token": bootstrap_token,
            "core_id": core_id,
            "canonical_origin": canonical_origin,
            "registration_key_id": existing.get("registration_key_id"),
        }
        response = await self._post(self._operation_url("revoke"), body)
        if response.status_code not in {200, 202, 204}:
            raise self._gateway_error(response)
        revoked = {
            key: value for key, value in existing.items()
            if key not in {"secret", "vapid_public_key", "subscription_endpoint", "delivery_endpoint", "lifecycle_endpoint"}
        }
        revoked.update({"state": "revoked", "scopes": [], "updated_at": datetime.now(timezone.utc).isoformat()})
        await self._settings.set_sensitive(self._credential_ref, revoked)
        return await self.status()

    async def _post(self, url: str, body: dict) -> httpx.Response:
        try:
            if self._client is not None:
                return await self._client.post(url, json=body, headers={"Content-Type": "application/json"})
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                return await client.post(url, json=body, headers={"Content-Type": "application/json"})
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise HTTPException(status_code=503, detail="notification_gateway_unavailable") from exc

    @staticmethod
    def _gateway_error(response: httpx.Response) -> HTTPException:
        try:
            candidate = str(response.json().get("error") or "")
        except Exception:
            candidate = ""
        detail = candidate if candidate in SAFE_GATEWAY_ERRORS else "notification_gateway_request_failed"
        status = response.status_code if response.status_code in {400, 401, 403, 409, 410, 422, 429} else 502
        return HTTPException(status_code=status, detail=detail)

    def _validate_response(self, value: GatewayProvisioningResponse, *, core_id: str, key_id: str) -> None:
        if value.core_id != core_id:
            raise HTTPException(status_code=502, detail="notification_gateway_wrong_core")
        if value.registration_key_id != key_id:
            raise HTTPException(status_code=502, detail="notification_gateway_key_mismatch")
        if value.gateway_audience != GATEWAY_AUDIENCE:
            raise HTTPException(status_code=502, detail="notification_gateway_audience_mismatch")
        if set(value.delivery_credential.scopes) != REQUIRED_DELIVERY_SCOPES or len(value.delivery_credential.scopes) != len(REQUIRED_DELIVERY_SCOPES):
            raise HTTPException(status_code=502, detail="notification_gateway_scope_mismatch")
        try:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", value.vapid_public_key):
                raise ValueError
            vapid = base64.urlsafe_b64decode(value.vapid_public_key + "=" * (-len(value.vapid_public_key) % 4))
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=502, detail="notification_gateway_vapid_key_invalid") from exc
        if len(vapid) != 65 or vapid[0] != 4:
            raise HTTPException(status_code=502, detail="notification_gateway_vapid_key_invalid")
        bootstrap_origin = httpx.URL(self._bootstrap_url).copy_with(path="/")
        required_paths = (
            (value.subscription_endpoint, "/v1/subscriptions"),
            (value.delivery_endpoint, "/v1/notifications"),
            (value.lifecycle_endpoint, f"/v1/cores/{core_id}"),
        )
        for raw, required_path in required_paths:
            try:
                endpoint = httpx.URL(raw)
            except Exception as exc:
                raise HTTPException(status_code=502, detail="notification_gateway_endpoint_invalid") from exc
            if endpoint.scheme != "https" or endpoint.userinfo or endpoint.query or endpoint.fragment:
                raise HTTPException(status_code=502, detail="notification_gateway_endpoint_invalid")
            if endpoint.copy_with(path="/") != bootstrap_origin:
                raise HTTPException(status_code=502, detail="notification_gateway_endpoint_origin_mismatch")
            if endpoint.path.rstrip("/") != required_path:
                raise HTTPException(status_code=502, detail="notification_gateway_endpoint_invalid")


def build_web_push_bootstrap_router(
    service: WebPushGatewayBootstrapService,
    keys: ServiceTokenKeyStore,
    users: UsersStore,
    settings: SettingsStore,
    audit: AuditLogStore | None = None,
) -> APIRouter:
    router = APIRouter()

    async def owner(body: OwnerBootstrapRequest, authorization: str | None):
        principal = await authenticate_human_token(authorization, keys, users)
        principal.require("ownership.manage")
        verified = await users.verify_credentials(principal.username, body.password)
        if verified is None or str(verified.get("user_id")) != principal.user_id:
            raise HTTPException(status_code=403, detail="reauthentication_failed")
        identity = await load_platform_identity(settings)
        return principal, identity

    async def record(event_type: str, principal, core_id: str, state: str) -> None:
        if audit is not None:
            await audit.record(event_type=event_type, actor_role=principal.role, actor_id=principal.user_id, details={"core_id": core_id, "state": state})

    @router.get("/notification-gateway/bootstrap/status")
    async def bootstrap_status(authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        principal.require("users.manage")
        return {"ok": True, **await service.status()}

    @router.post("/notification-gateway/bootstrap")
    async def bootstrap(body: OwnerBootstrapRequest, authorization: str | None = Header(default=None)):
        principal, identity = await owner(body, authorization)
        result = await service.provision(operation="bootstrap", bootstrap_token=body.bootstrap_token, core_id=identity.core_id, canonical_origin=f"https://{identity.public_hostname}")
        await record("web_push_gateway_bootstrapped", principal, identity.core_id, "active")
        return {"ok": True, **result}

    @router.post("/notification-gateway/bootstrap/rotate")
    async def rotate(body: OwnerBootstrapRequest, authorization: str | None = Header(default=None)):
        principal, identity = await owner(body, authorization)
        result = await service.provision(operation="rotate", bootstrap_token=body.bootstrap_token, core_id=identity.core_id, canonical_origin=f"https://{identity.public_hostname}")
        await record("web_push_gateway_bootstrap_rotated", principal, identity.core_id, "active")
        return {"ok": True, **result}

    @router.post("/notification-gateway/bootstrap/revoke")
    async def revoke(body: OwnerBootstrapRequest, authorization: str | None = Header(default=None)):
        principal, identity = await owner(body, authorization)
        result = await service.revoke(bootstrap_token=body.bootstrap_token, core_id=identity.core_id, canonical_origin=f"https://{identity.public_hostname}")
        await record("web_push_gateway_bootstrap_revoked", principal, identity.core_id, "revoked")
        return {"ok": True, **result}

    return router
