from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Header

from app.system.settings.store import SettingsStore
from app.system.auth.device_enrollment import WebAppEnrollmentStore
from app.system.auth.human import authenticate_human_token
from app.system.auth.tokens import ServiceTokenKeyStore
from app.system.users.store import UsersStore
from app.system.audit import AuditLogStore
from .web_notification_policy import NotificationIntentStore


GATEWAY_CONTRACT_VERSION = "hexe.web-push-gateway.v1"


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


class GatewayCredentialMaterial(NamedTuple):
    secret: str
    version: str


class WebPushGatewayPublisher:
    def __init__(self, intents: NotificationIntentStore, devices: WebAppEnrollmentStore, settings: SettingsStore, *, core_id: str, gateway_url: str, credential_ref: str, audience: str, client: httpx.AsyncClient | None = None, max_attempts: int = 8) -> None:
        self._intents = intents
        self._devices = devices
        self._settings = settings
        self._core_id = core_id
        self._gateway_url = self._validated_gateway_url(gateway_url)
        self._notification_url = f"{self._gateway_url}/v1/notifications" if self._gateway_url else ""
        self._subscription_url = f"{self._gateway_url}/v1/subscriptions" if self._gateway_url else ""
        self._credential_ref = credential_ref
        self._audience = audience
        self._client = client
        self._max_attempts = max(1, max_attempts)

    @staticmethod
    def _validated_gateway_url(value: str) -> str:
        try:
            parsed = httpx.URL(str(value or "").strip())
        except Exception:
            return ""
        if parsed.scheme != "https" or not parsed.host or parsed.userinfo or parsed.query or parsed.fragment:
            return ""
        return str(parsed).rstrip("/")

    async def publish_due(self, *, now: datetime | None = None) -> dict[str, int]:
        selected_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        rows = await self._intents.due(selected_now.isoformat())
        counts = {"accepted": 0, "retry": 0, "dead": 0, "invalid_subscription": 0}
        await self._refresh_provisioned_configuration()
        credential = await self._credential("notification.publish")
        if credential is None or not self._notification_url:
            return counts
        for row in rows:
            outcome = await self._publish_one(row, credential, selected_now)
            counts[outcome] += 1
        return counts

    async def cleanup_due(self, *, now: datetime | None = None) -> dict[str, int]:
        selected_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        counts = {"deleted": 0, "retry": 0, "failed": 0}
        await self._refresh_provisioned_configuration()
        credential = await self._credential("notification.subscription.delete")
        if credential is None or not self._subscription_url:
            return counts
        for row in await self._devices.pending_notification_cleanup(core_id=self._core_id):
            ref = str(row["subscription_ref"])
            issued = int(selected_now.timestamp())
            headers = {
                "Authorization": self._authorization_assertion(
                    credential,
                    scope="notification.subscription.delete",
                    body=b"",
                    issued=issued,
                ),
                "Idempotency-Key": f"{self._core_id}:subscription-delete:{row['device_id']}:{hashlib.sha256(ref.encode()).hexdigest()}",
            }
            try:
                path = f"{self._subscription_url}/{quote(ref, safe='')}"
                if self._client is not None:
                    response = await self._client.delete(path, headers=headers)
                else:
                    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                        response = await client.delete(path, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError):
                counts["retry"] += 1
                continue
            if response.status_code in {200, 202, 204, 404, 410}:
                await self._devices.mark_notification_cleanup_complete(device_id=str(row["device_id"]), core_id=self._core_id, subscription_ref=ref)
                counts["deleted"] += 1
            elif response.status_code in {408, 425, 429} or response.status_code >= 500:
                counts["retry"] += 1
            else:
                counts["failed"] += 1
        return counts

    async def _refresh_provisioned_configuration(self) -> None:
        value = await self._settings.get_sensitive(self._credential_ref)
        if not isinstance(value, dict) or value.get("state") != "active" or value.get("core_id") != self._core_id:
            return
        notification_url = self._validated_gateway_url(str(value.get("delivery_endpoint") or ""))
        subscription_url = self._validated_gateway_url(str(value.get("subscription_endpoint") or ""))
        audience = str(value.get("gateway_audience") or "").strip()
        if notification_url and subscription_url and audience:
            self._notification_url = notification_url
            self._subscription_url = subscription_url
            self._audience = audience

    async def _credential(self, required_scope: str = "notification.publish") -> GatewayCredentialMaterial | None:
        value = await self._settings.get_sensitive(self._credential_ref)
        if not isinstance(value, dict):
            value = await self._settings.get(self._credential_ref)
        if isinstance(value, dict):
            if value.get("core_id") != self._core_id or required_scope not in set(value.get("scopes") or []):
                return None
            if value.get("state") not in {None, "active"}:
                return None
            secret = str(value.get("secret") or "")
            version = str(value.get("credential_version") or "").strip()
            return GatewayCredentialMaterial(secret, version) if len(secret) >= 32 and version else None
        return None

    def _authorization_assertion(self, credential: GatewayCredentialMaterial, *, scope: str, body: bytes, issued: int) -> str:
        assertion_payload = {
            "iss": self._core_id,
            "sub": self._core_id,
            "core_id": self._core_id,
            "aud": self._audience,
            "scp": [scope],
            "credential_version": credential.version,
            "iat": issued,
            "exp": issued + 60,
            "jti": secrets.token_urlsafe(18),
            "body_sha256": hashlib.sha256(body).hexdigest(),
        }
        assertion_raw = _b64url(json.dumps(assertion_payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        signature = _b64url(hmac.new(credential.secret.encode("utf-8"), assertion_raw.encode("ascii"), hashlib.sha256).digest())
        return f"HexeAssertion {assertion_raw}.{signature}"

    async def _publish_one(self, row: dict[str, Any], credential: GatewayCredentialMaterial, now: datetime) -> str:
        expires = now + timedelta(minutes=10)
        body = {
            "contract_version": GATEWAY_CONTRACT_VERSION,
            "event_id": row["event_id"], "core_id": self._core_id,
            "subscription_ref": row["subscription_ref"], "category": row["category"],
            "title": row["title"], "body": row["body"],
            "navigation_path": row["navigation_path"], "privacy_level": row["privacy_level"],
            "severity": row["severity"], "expiry": expires.isoformat(),
            "badge_count": int(row.get("coalesced_count") or 1),
        }
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        issued = int(now.timestamp())
        headers = {"Authorization": self._authorization_assertion(credential, scope="notification.publish", body=encoded, issued=issued), "Idempotency-Key": f"{self._core_id}:{row['event_id']}:{row['device_id']}:{row['category']}", "Content-Type": "application/json"}
        attempts = int(row.get("attempt_count") or 0) + 1
        try:
            if self._client is not None:
                response = await self._client.post(self._notification_url, content=encoded, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                    response = await client.post(self._notification_url, content=encoded, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError):
            return await self._retry(row, attempts, now, "gateway_unavailable")
        if response.status_code in {200, 201, 202, 204, 409}:
            await self._intents.mark_delivery(int(row["intent_id"]), status="delivered", attempt_count=attempts, delivered_at=now.isoformat())
            return "accepted"
        if response.status_code in {404, 410}:
            await self._devices.delete_notification_subscription(device_id=str(row["device_id"]), core_id=self._core_id, user_id=str(row["user_id"]))
            await self._intents.mark_delivery(int(row["intent_id"]), status="dead", attempt_count=attempts, last_error="invalid_subscription")
            return "invalid_subscription"
        if response.status_code in {408, 425, 429} or response.status_code >= 500:
            return await self._retry(row, attempts, now, "rate_limited" if response.status_code == 429 else "gateway_retryable")
        error = "gateway_authentication_failed" if response.status_code in {401, 403} else "gateway_permanent_failure"
        await self._intents.mark_delivery(int(row["intent_id"]), status="dead", attempt_count=attempts, last_error=error)
        return "dead"

    async def _retry(self, row: dict[str, Any], attempts: int, now: datetime, error: str) -> str:
        if attempts >= self._max_attempts:
            await self._intents.mark_delivery(int(row["intent_id"]), status="dead", attempt_count=attempts, last_error=error)
            return "dead"
        delay = min(3600, 2 ** attempts) + secrets.randbelow(3)
        await self._intents.mark_delivery(int(row["intent_id"]), status="retry", attempt_count=attempts, next_attempt_at=(now + timedelta(seconds=delay)).isoformat(), last_error=error)
        return "retry"

    async def safe_status(self) -> dict[str, Any]:
        await self._refresh_provisioned_configuration()
        return {"configured": bool(self._notification_url and await self._credential()), "counts": await self._intents.status_counts()}

def build_web_push_gateway_router(publisher: WebPushGatewayPublisher, keys: ServiceTokenKeyStore, users: UsersStore, audit: AuditLogStore | None = None) -> APIRouter:
    router = APIRouter()

    @router.get("/notification-gateway/status")
    async def gateway_status(authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        principal.require("users.manage")
        return {"ok": True, **await publisher.safe_status()}

    return router
