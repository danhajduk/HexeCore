import asyncio
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin import configure_admin_users_store, router as admin_router
from app.system.auth import ServiceTokenKeyStore, sign_hs256
from app.system.management_access import ManagementAuthorizationService, ManagementAuthorizationStore, build_management_access_router
from app.system.onboarding import NodeRegistrationsStore, NodeTrustIssuanceService, NodeTrustStore
from app.system.onboarding.registrations import NodeRegistrationRecord
from app.system.users import UsersStore


class _Settings:
    def __init__(self): self.data = {}
    async def get(self, key): return self.data.get(key)
    async def set(self, key, value): self.data[key] = value


def _registration(node_id: str, status: str = "trusted") -> NodeRegistrationRecord:
    now = "2026-09-27T00:00:00+00:00"
    return NodeRegistrationRecord(node_id=node_id, node_type="ai-node", node_name=node_id,
        node_software_version="1", requested_node_type="ai-node", capabilities_summary=[],
        trust_status=status, source_onboarding_session_id=f"session-{node_id}",
        approved_by_user_id="admin", approved_at=now, created_at=now, updated_at=now)


class TestNodeManagementAccessApi:
    def setup_method(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.keys = ServiceTokenKeyStore(_Settings())
        self.trust = NodeTrustIssuanceService(NodeTrustStore(root / "trust.json"))
        self.registrations = NodeRegistrationsStore(path=root / "registrations.json")
        self.users = UsersStore(str(root / "users.db"))
        configure_admin_users_store(self.users)
        self.store = ManagementAuthorizationStore(root / "management.json")
        self.service = ManagementAuthorizationService(keys=self.keys, store=self.store)
        self.node_id, self.node_token = self._trusted("node-ai")
        self.other_id, self.other_token = self._trusted("node-voice")
        self.env = patch.dict(os.environ, {"HEXE_ADMIN_TOKEN": "admin-test"}, clear=False)
        self.env.start()
        app = FastAPI()
        app.include_router(admin_router, prefix="/api")
        app.include_router(build_management_access_router(service=self.service, trust=self.trust,
            registrations=self.registrations, users=self.users), prefix="/api")
        self.client = TestClient(app)

    def teardown_method(self):
        self.env.stop()
        self.tmp.cleanup()

    def _trusted(self, node_id):
        activation = self.trust.reissue_for_node(node_id=node_id, node_type="ai-node", source_session_id=f"session-{node_id}")["activation"]
        self.registrations.upsert(_registration(node_id))
        return node_id, activation["node_trust_token"]

    def _issue(self, scopes=None, node_id=None):
        return self.client.post("/api/system/nodes/management/authorize", headers={"X-Admin-Token": "admin-test"},
            json={"target_node_id": node_id or self.node_id, "required_scopes": scopes or ["node.manage.read"]})

    def _inspect(self, token, scopes=None, node_id=None, trust_token=None):
        return self.client.post("/api/system/nodes/management/introspect",
            headers={"X-Node-Id": node_id or self.node_id, "X-Node-Trust-Token": trust_token or self.node_token},
            json={"token": token, "required_scopes": scopes or []})

    def test_authorized_operator_for_correct_node(self):
        issued = self._issue(["node.manage.configuration", "node.manage.read"])
        assert issued.status_code == 200
        body = self._inspect(issued.json()["token"], ["node.manage.configuration"]).json()
        assert body["active"] is True
        assert body["claims"]["sub"] == "admin_token"
        assert body["claims"]["aud"] == f"node-management:{self.node_id}"

    def test_unauthorized_operator_and_unsupported_permission(self):
        assert self.client.post("/api/system/nodes/management/authorize", json={"target_node_id": self.node_id, "required_scopes": ["node.manage.read"]}).status_code == 401
        assert self._issue(["service.execute:task.image_generation"]).status_code == 422

    def test_wrong_node_and_insufficient_permission(self):
        token = self._issue().json()["token"]
        wrong = self._inspect(token, node_id=self.other_id, trust_token=self.other_token)
        assert wrong.json()["error_code"] == "management_target_mismatch"
        denied = self._inspect(token, ["node.manage.credentials"])
        assert denied.json()["error_code"] == "management_scope_insufficient"

    def test_revoked_and_expired_authorization(self):
        issued = self._issue().json()
        revoked = self.client.post(f"/api/system/nodes/management/authorizations/{issued['authorization_id']}/revoke", headers={"X-Admin-Token": "admin-test"})
        assert revoked.status_code == 200
        assert self._inspect(issued["token"]).json()["error_code"] == "management_authorization_revoked"
        key = asyncio.run(self.keys.active_key())
        now = int(time.time())
        claims = {**issued["claims"], "iat": now - 100, "exp": now - 60, "jti": "expired"}
        expired = sign_hs256({"alg": "HS256", "typ": "JWT", "kid": key["kid"]}, claims, str(key["secret"]))
        assert self._inspect(expired).json()["error_code"] == "token_expired"

    def test_untrusted_node_and_workload_token_misuse(self):
        token = self._issue().json()["token"]
        assert self._inspect(token, trust_token="wrong").status_code == 403
        key = asyncio.run(self.keys.active_key())
        now = int(time.time())
        workload = sign_hs256({"alg": "HS256", "typ": "JWT", "kid": key["kid"]}, {
            "iss": "hexe-core", "token_use": "node_service", "authorization_id": "x", "provider_node_id": self.node_id,
            "sub": "node-caller", "aud": f"node-management:{self.node_id}", "scp": ["node.manage.read"],
            "iat": now, "exp": now + 60, "jti": "workload"}, str(key["secret"]))
        assert self._inspect(workload).json()["error_code"] == "token_use_invalid"

    def test_untrusted_target_cannot_receive_authorization(self):
        self.registrations.upsert(_registration("damaged-node", "revoked"))
        response = self._issue(node_id="damaged-node")
        assert response.status_code == 409
        assert response.json()["detail"] == "management_target_node_untrusted"

    def test_validation_unavailable_fails_closed(self):
        token = self._issue().json()["token"]
        with patch.object(self.keys, "verification_keys", new=AsyncMock(side_effect=RuntimeError("offline"))):
            response = self._inspect(token)
        assert response.status_code == 503
        assert response.json()["detail"] == "management_validation_unavailable"

    def test_disabled_operator_invalidates_outstanding_authorization(self):
        asyncio.run(self.users.upsert_user(username="operator", role="admin", enabled=True, password="secret"))
        asyncio.run(self.users.upsert_user(username="backup", role="admin", enabled=True, password="secret"))
        token, _ = asyncio.run(self.service.issue(operator_id="operator", operator_role="admin",
            target_node_id=self.node_id, scopes=["node.manage.read"]))
        assert self._inspect(token).json()["active"] is True

        asyncio.run(self.users.upsert_user(username="operator", role="admin", enabled=False, password=None))

        denied = self._inspect(token).json()
        assert denied["active"] is False
        assert denied["error_code"] == "operator_access_revoked"

    def test_enabled_owner_authorization_remains_active(self):
        asyncio.run(self.users.upsert_user(username="owner-operator", role="owner", enabled=True, password="secret"))
        token, _ = asyncio.run(self.service.issue(operator_id="owner-operator", operator_role="owner",
            target_node_id=self.node_id, scopes=["node.manage.read"]))

        inspected = self._inspect(token).json()

        assert inspected["active"] is True
        assert inspected["claims"]["sub"] == "owner-operator"

    def test_cookie_authorization_requires_same_origin_csrf(self):
        asyncio.run(self.users.upsert_user(username="browser-admin", role="admin", enabled=True, password="secret"))
        login = self.client.post("/api/admin/session/login-user", json={"username": "browser-admin", "password": "secret"})
        assert login.status_code == 200
        payload = {"target_node_id": self.node_id, "required_scopes": ["node.manage.read"]}

        missing = self.client.post("/api/system/nodes/management/authorize", json=payload)
        assert missing.status_code == 403
        assert missing.json()["detail"] == "csrf_origin_required"

        foreign = self.client.post("/api/system/nodes/management/authorize", headers={"Origin": "https://evil.example"}, json=payload)
        assert foreign.status_code == 403
        assert foreign.json()["detail"] == "csrf_origin_mismatch"

        allowed = self.client.post("/api/system/nodes/management/authorize", headers={"Origin": "http://testserver"}, json=payload)
        assert allowed.status_code == 200
