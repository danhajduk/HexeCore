from __future__ import annotations

import base64
import asyncio
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Literal

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.system.auth.device_enrollment import WebAppEnrollmentStore
from app.system.auth.human import authenticate_human_token
from app.system.auth.tokens import ServiceTokenKeyStore
from app.system.platform_identity import load_platform_identity
from app.system.settings.store import SettingsStore
from app.system.users.store import UsersStore


REGISTRATION_CONTRACT_VERSION = "hexe.web-push-registration.v1"
_SIGNING_KEY_REF = "web_push_registration_signing_key_v1"


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _gateway_url(value: str) -> str:
    try:
        parsed = httpx.URL(str(value or "").strip())
    except Exception:
        return ""
    if parsed.scheme != "https" or not parsed.host or parsed.userinfo or parsed.query or parsed.fragment:
        return ""
    return str(parsed).rstrip("/")


def verify_registration_grant(
    grant: str,
    public_key: str,
    *,
    core_id: str,
    user_id: str,
    device_id: str,
    audience: str,
    operation: str,
    seen_jtis: set[str],
    now: int | None = None,
) -> dict:
    try:
        encoded_header, encoded_claims, encoded_signature = grant.split(".")
        signing_input = f"{encoded_header}.{encoded_claims}"
        decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        header = json.loads(decode(encoded_header))
        claims = json.loads(decode(encoded_claims))
        Ed25519PublicKey.from_public_bytes(decode(public_key)).verify(decode(encoded_signature), signing_input.encode())
    except (ValueError, TypeError, json.JSONDecodeError, InvalidSignature) as exc:
        raise ValueError("registration_grant_invalid") from exc
    selected_now = int(time.time()) if now is None else int(now)
    expected = {
        "iss": core_id,
        "sub": user_id,
        "core_id": core_id,
        "user_id": user_id,
        "device_id": device_id,
        "aud": audience,
        "operation": operation,
        "token_use": "web_push_subscription",
    }
    if header.get("alg") != "EdDSA" or any(claims.get(key) != value for key, value in expected.items()):
        raise ValueError("registration_grant_claims_invalid")
    if int(claims.get("iat", 0)) > selected_now + 30 or int(claims.get("exp", 0)) <= selected_now:
        raise ValueError("registration_grant_expired")
    jti = str(claims.get("jti") or "")
    if not jti or jti in seen_jtis:
        raise ValueError("registration_grant_replayed")
    seen_jtis.add(jti)
    return claims


class RegistrationGrantRequest(BaseModel):
    operation: Literal["register", "delete"]


class WebPushRegistrationGrantIssuer:
    def __init__(
        self,
        settings: SettingsStore,
        *,
        gateway_url: str,
        gateway_audience: str,
        vapid_public_key: str,
        ttl_seconds: int = 120,
    ) -> None:
        self._settings = settings
        self.gateway_url = _gateway_url(gateway_url)
        self.gateway_audience = str(gateway_audience or "").strip()
        self.vapid_public_key = str(vapid_public_key or "").strip()
        self.ttl_seconds = max(30, min(int(ttl_seconds), 300))
        self._key_lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.gateway_url and self.gateway_audience and self.vapid_public_key)

    async def _private_key(self) -> Ed25519PrivateKey:
        async with self._key_lock:
            saved = await self._settings.get(_SIGNING_KEY_REF)
            encoded = str(saved.get("private_key") or "") if isinstance(saved, dict) else ""
            if encoded:
                try:
                    raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
                    return Ed25519PrivateKey.from_private_bytes(raw)
                except (TypeError, ValueError):
                    pass
            key = Ed25519PrivateKey.generate()
            raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
            await self._settings.set(_SIGNING_KEY_REF, {"private_key": _b64url(raw), "created_at": datetime.now(timezone.utc).isoformat()})
            return key

    async def public_key(self) -> str:
        key = await self._private_key()
        raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return _b64url(raw)

    async def issue(self, *, core_id: str, user_id: str, device_id: str, operation: str) -> tuple[str, dict]:
        now = int(time.time())
        claims = {
            "iss": core_id,
            "sub": user_id,
            "core_id": core_id,
            "user_id": user_id,
            "device_id": device_id,
            "aud": self.gateway_audience,
            "operation": operation,
            "token_use": "web_push_subscription",
            "iat": now,
            "exp": now + self.ttl_seconds,
            "jti": secrets.token_urlsafe(24),
        }
        header = {"alg": "EdDSA", "typ": "JWT", "kid": f"{core_id}:web-push-registration:v1"}
        signing_input = f"{_b64url(json.dumps(header, sort_keys=True, separators=(',', ':')).encode())}.{_b64url(json.dumps(claims, sort_keys=True, separators=(',', ':')).encode())}"
        signature = await self._private_key()
        return f"{signing_input}.{_b64url(signature.sign(signing_input.encode()))}", claims


def build_web_push_registration_router(
    issuer: WebPushRegistrationGrantIssuer,
    keys: ServiceTokenKeyStore,
    users: UsersStore,
    devices: WebAppEnrollmentStore,
    settings: SettingsStore,
) -> APIRouter:
    router = APIRouter()

    async def enrolled(authorization: str | None):
        principal = await authenticate_human_token(authorization, keys, users)
        if not principal.device_id:
            raise HTTPException(status_code=403, detail="enrolled_device_required")
        device = await devices.get_device(principal.device_id)
        identity = await load_platform_identity(settings)
        if device is None or device.get("revoked_at") or not bool(device.get("enabled", True)):
            raise HTTPException(status_code=403, detail="enrolled_device_invalid")
        if str(device.get("user_id") or "") != principal.user_id:
            raise HTTPException(status_code=403, detail="enrolled_device_invalid")
        if str(device.get("core_id") or "") != identity.core_id:
            raise HTTPException(status_code=403, detail="enrolled_device_wrong_core")
        return principal, device, identity

    @router.get("/notification-subscriptions/config")
    async def registration_config(authorization: str | None = Header(default=None)):
        _, _, identity = await enrolled(authorization)
        return {
            "contract_version": REGISTRATION_CONTRACT_VERSION,
            "configured": issuer.configured,
            "core_id": identity.core_id,
            "gateway_url": issuer.gateway_url if issuer.configured else None,
            "gateway_audience": issuer.gateway_audience,
            "vapid_public_key": issuer.vapid_public_key if issuer.configured else None,
            "grant_public_key": await issuer.public_key(),
            "grant_algorithm": "EdDSA",
        }

    @router.post("/notification-subscriptions/grants")
    async def issue_grant(body: RegistrationGrantRequest, authorization: str | None = Header(default=None)):
        principal, device, identity = await enrolled(authorization)
        if not issuer.configured:
            raise HTTPException(status_code=503, detail="notification_gateway_registration_unavailable")
        subscription = await devices.get_notification_subscription(
            device_id=str(device["device_id"]), core_id=identity.core_id, user_id=principal.user_id
        )
        subscription_ref = subscription.get("subscription_ref") if subscription else None
        if body.operation == "delete" and not subscription_ref:
            raise HTTPException(status_code=409, detail="notification_subscription_absent")
        grant, claims = await issuer.issue(
            core_id=identity.core_id,
            user_id=principal.user_id,
            device_id=str(device["device_id"]),
            operation=body.operation,
        )
        return {
            "contract_version": REGISTRATION_CONTRACT_VERSION,
            "grant": grant,
            "expires_at": datetime.fromtimestamp(claims["exp"], timezone.utc).isoformat(),
            "gateway_url": issuer.gateway_url,
            "gateway_audience": issuer.gateway_audience,
            "subscription_ref": subscription_ref if body.operation == "delete" else None,
        }

    return router
