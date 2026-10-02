import asyncio
import base64
import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.web_push_bootstrap import WebPushGatewayBootstrapService, build_web_push_bootstrap_router
from app.core.web_push_registration import WebPushRegistrationGrantIssuer
from app.system.auth import ServiceTokenKeyStore, build_human_auth_router
from app.system.settings.router import build_settings_router
from app.system.settings.store import SettingsStore
from app.system.users import UsersStore


CORE_ID = "0123456789abcdef"
BOOTSTRAP_URL = "https://gateway.example/v1/cores/bootstrap"
SECRET_ONE = "first-delivery-secret-that-never-leaves-core"
SECRET_TWO = "rotated-delivery-secret-that-never-leaves-core"
VAPID_PUBLIC_KEY = base64.urlsafe_b64encode(b"\x04" + b"v" * 64).decode().rstrip("=")


def gateway_response(request: httpx.Request, *, secret: str = SECRET_ONE, version: str = "v1", scopes=None, core_id: str | None = None):
    body = json.loads(request.content)
    return httpx.Response(201, json={
        "contract_version": "hexe.web-push-gateway-bootstrap.v1",
        "core_id": core_id or body["core_id"],
        "state": "active",
        "gateway_audience": "hexe-notification-gateway",
        "vapid_public_key": VAPID_PUBLIC_KEY,
        "subscription_endpoint": "https://gateway.example/v1/subscriptions",
        "delivery_endpoint": "https://gateway.example/v1/notifications",
        "rotation_endpoint": "https://gateway.example/v1/cores/rotate",
        "revocation_endpoint": "https://gateway.example/v1/cores/revoke",
        "registration_contract_version": "hexe.web-push-registration.v1",
        "delivery_contract_version": "hexe.web-push-gateway.v1",
        "registration_key_id": body["registration_key_id"],
        "delivery_credential": {
            "version": version,
            "secret": secret,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "scopes": scopes or ["notification.publish", "notification.subscription.delete"],
        },
    })


class BootstrapFixture:
    def __init__(self, handler):
        self.temporary = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"HEXE_CORE_ID": CORE_ID, "PLATFORM_DOMAIN": "hexe-ai.com"}, clear=False)
        self.environment.start()
        self.settings = SettingsStore(os.path.join(self.temporary.name, "settings.db"))
        asyncio.run(self.settings.set("platform.core_id", CORE_ID))
        asyncio.run(self.settings.set("core.id", CORE_ID))
        self.users = UsersStore(os.path.join(self.temporary.name, "users.db"))
        asyncio.run(self.users.upsert_user(username="Owner", role="owner", enabled=True, password="owner-pass"))
        asyncio.run(self.users.upsert_user(username="Member", role="member", enabled=True, password="member-pass"))
        self.keys = ServiceTokenKeyStore(self.settings)
        self.issuer = WebPushRegistrationGrantIssuer(self.settings, gateway_url="", gateway_audience="hexe-notification-gateway", vapid_public_key="")
        self.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.service = WebPushGatewayBootstrapService(self.settings, self.issuer, bootstrap_url=BOOTSTRAP_URL, client=self.http)
        app = FastAPI()
        app.include_router(build_human_auth_router(self.keys, self.users), prefix="/api/auth")
        app.include_router(build_settings_router(self.settings), prefix="/api/system")
        app.include_router(build_web_push_bootstrap_router(self.service, self.keys, self.users, self.settings), prefix="/api/web-app")
        self.client = TestClient(app)
        owner = self.client.post("/api/auth/user/login", json={"username": "Owner", "password": "owner-pass"}).json()
        member = self.client.post("/api/auth/user/login", json={"username": "Member", "password": "member-pass"}).json()
        self.owner = {"Authorization": f"Bearer {owner['access_token']}"}
        self.member = {"Authorization": f"Bearer {member['access_token']}"}

    def close(self):
        asyncio.run(self.http.aclose())
        self.environment.stop()
        self.temporary.cleanup()


def test_owner_step_up_bootstrap_stores_secret_only_in_sensitive_settings():
    requests = []
    def handler(request):
        requests.append(request)
        return gateway_response(request)
    fixture = BootstrapFixture(handler)
    try:
        denied_role = fixture.client.post("/api/web-app/notification-gateway/bootstrap", headers=fixture.member, json={"password": "member-pass", "bootstrap_token": "t" * 32})
        assert denied_role.status_code == 403
        denied_password = fixture.client.post("/api/web-app/notification-gateway/bootstrap", headers=fixture.owner, json={"password": "wrong", "bootstrap_token": "t" * 32})
        assert denied_password.status_code == 403
        response = fixture.client.post("/api/web-app/notification-gateway/bootstrap", headers=fixture.owner, json={"password": "owner-pass", "bootstrap_token": "t" * 32})
        assert response.status_code == 200, response.text
        assert SECRET_ONE not in response.text
        assert "bootstrap_token" not in response.text
        sent = json.loads(requests[0].content)
        assert sent["core_id"] == CORE_ID
        assert sent["canonical_origin"] == f"https://{CORE_ID}.hexe-ai.com"
        assert sent["registration_key_id"] == f"{CORE_ID}:web-push-registration:v1"
        assert sent["registration_public_key"] == asyncio.run(fixture.issuer.public_key())
        assert requests[0].headers.get("authorization") is None
        assert "t" * 32 not in str(requests[0].url)
        record = asyncio.run(fixture.settings.get_sensitive("notification_gateway_credential"))
        assert record["secret"] == SECRET_ONE
        ordinary = fixture.client.get("/api/system/settings")
        assert SECRET_ONE not in ordinary.text
        assert "notification_gateway_credential" not in ordinary.text
    finally:
        fixture.close()


def test_gateway_expiry_replay_wrong_core_and_duplicate_errors_are_safe():
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body["bootstrap_token"])
        token = body["bootstrap_token"]
        if token.startswith("expired"):
            return httpx.Response(410, json={"error": "bootstrap_expired", "token": token})
        if token.startswith("replayed"):
            return httpx.Response(409, json={"error": "bootstrap_replayed"})
        if token.startswith("wrongcore"):
            return gateway_response(request, core_id="fedcba9876543210")
        return gateway_response(request)
    fixture = BootstrapFixture(handler)
    try:
        for token, expected in (("expired" + "x" * 25, "bootstrap_expired"), ("replayed" + "x" * 24, "bootstrap_replayed"), ("wrongcore" + "x" * 24, "notification_gateway_wrong_core")):
            response = fixture.client.post("/api/web-app/notification-gateway/bootstrap", headers=fixture.owner, json={"password": "owner-pass", "bootstrap_token": token})
            assert response.json()["detail"] == expected
            assert token not in response.text
        accepted = fixture.client.post("/api/web-app/notification-gateway/bootstrap", headers=fixture.owner, json={"password": "owner-pass", "bootstrap_token": "accepted" + "x" * 24})
        assert accepted.status_code == 200
        before = len(calls)
        duplicate = fixture.client.post("/api/web-app/notification-gateway/bootstrap", headers=fixture.owner, json={"password": "owner-pass", "bootstrap_token": "duplicate" + "x" * 24})
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"] == "core_already_registered"
        assert len(calls) == before
    finally:
        fixture.close()


def test_scope_restriction_rotation_and_immediate_revocation():
    version = {"value": 0}
    requested_urls = []
    def handler(request):
        requested_urls.append(str(request.url))
        body = json.loads(request.content)
        if body["operation"] == "revoke":
            return httpx.Response(204)
        version["value"] += 1
        if body["bootstrap_token"].startswith("badscope"):
            return gateway_response(request, scopes=["notification.publish"])
        secret = SECRET_ONE if version["value"] == 1 else SECRET_TWO
        return gateway_response(request, secret=secret, version=f"v{version['value']}")
    fixture = BootstrapFixture(handler)
    try:
        bad = fixture.client.post("/api/web-app/notification-gateway/bootstrap", headers=fixture.owner, json={"password": "owner-pass", "bootstrap_token": "badscope" + "x" * 24})
        assert bad.status_code == 502
        assert bad.json()["detail"] == "notification_gateway_scope_mismatch"
        first = fixture.client.post("/api/web-app/notification-gateway/bootstrap", headers=fixture.owner, json={"password": "owner-pass", "bootstrap_token": "first" + "x" * 27})
        assert first.status_code == 200
        old_public = asyncio.run(fixture.issuer.public_key())
        rotated = fixture.client.post("/api/web-app/notification-gateway/bootstrap/rotate", headers=fixture.owner, json={"password": "owner-pass", "bootstrap_token": "rotate" + "x" * 26})
        assert rotated.status_code == 200, rotated.text
        assert requested_urls[-1] == "https://gateway.example/v1/cores/rotate"
        assert rotated.json()["credential_version"] == "v3"
        assert asyncio.run(fixture.issuer.public_key()) != old_public
        record = asyncio.run(fixture.settings.get_sensitive("notification_gateway_credential"))
        assert record["secret"] == SECRET_TWO
        revoked = fixture.client.post("/api/web-app/notification-gateway/bootstrap/revoke", headers=fixture.owner, json={"password": "owner-pass", "bootstrap_token": "revoke" + "x" * 26})
        assert revoked.status_code == 200, revoked.text
        assert requested_urls[-1] == "https://gateway.example/v1/cores/revoke"
        assert revoked.json()["state"] == "revoked"
        assert revoked.json()["configured"] is False
        record = asyncio.run(fixture.settings.get_sensitive("notification_gateway_credential"))
        assert "secret" not in record
        assert (asyncio.run(fixture.issuer.runtime_configuration()))["configured"] is False
        assert SECRET_ONE not in fixture.client.get("/api/web-app/notification-gateway/bootstrap/status", headers=fixture.owner).text
        assert SECRET_TWO not in fixture.client.get("/api/web-app/notification-gateway/bootstrap/status", headers=fixture.owner).text
    finally:
        fixture.close()


def test_lifecycle_endpoints_must_be_exact_and_same_origin():
    def handler(request):
        response = gateway_response(request)
        payload = response.json()
        payload["rotation_endpoint"] = "https://attacker.example/v1/cores/rotate"
        return httpx.Response(201, json=payload)

    fixture = BootstrapFixture(handler)
    try:
        response = fixture.client.post(
            "/api/web-app/notification-gateway/bootstrap",
            headers=fixture.owner,
            json={"password": "owner-pass", "bootstrap_token": "endpoint" + "x" * 24},
        )
        assert response.status_code == 502
        assert response.json()["detail"] == "notification_gateway_endpoint_origin_mismatch"
        assert asyncio.run(fixture.settings.get_sensitive("notification_gateway_credential")) is None
    finally:
        fixture.close()
