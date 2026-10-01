import os
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin import _build_session_cookie
from app.remote_web_boundary import RemoteWebBoundaryMiddleware


class Settings:
    def __init__(self):
        self.data = {"platform.core_id": "0123456789abcdef", "platform.domain": "hexe-ai.com"}

    async def get_all(self):
        return dict(self.data)

    async def set(self, key, value):
        self.data[key] = value


def client(*, rate_limit_per_minute=None, sensitive_auth_rate_limit_per_minute=None):
    app = FastAPI()
    app.state.settings_store = Settings()
    middleware_options = {}
    if rate_limit_per_minute is not None:
        middleware_options["rate_limit_per_minute"] = rate_limit_per_minute
    if sensitive_auth_rate_limit_per_minute is not None:
        middleware_options["sensitive_auth_rate_limit_per_minute"] = sensitive_auth_rate_limit_per_minute
    app.add_middleware(RemoteWebBoundaryMiddleware, **middleware_options)

    @app.get("/{path:path}")
    async def route(path: str):
        return {"path": f"/{path}"}

    return TestClient(app)


def test_public_root_redirects_to_app_and_never_serves_dashboard():
    response = client().get("/", headers={"Host": "0123456789abcdef.hexe-ai.com"}, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/app"


def test_local_root_remains_dashboard_route():
    response = client().get("/", headers={"Host": "192.168.1.20:9001"})
    assert response.status_code == 200
    assert response.json() == {"path": "/"}


def test_remote_alias_is_not_supported_on_any_host():
    response = client().get("/remote/setup", headers={"Host": "0123456789abcdef.hexe-ai.com"})
    assert response.status_code == 404


def test_untrusted_forwarded_host_does_not_override_direct_host():
    response = client().get("/", headers={"Host": "192.168.1.20", "X-Forwarded-Host": "0123456789abcdef.hexe-ai.com"})
    # TestClient's peer is not an explicitly trusted loopback proxy.
    assert response.status_code == 200


def test_invalid_host_fails_closed():
    response = client().get("/", headers={"Host": "bad.example,other.example"})
    assert response.status_code == 400


def test_public_web_app_preflight_allows_exact_core_origin_and_authorization():
    response = client().options(
        "/api/web-app/bootstrap",
        headers={
            "Host": "0123456789abcdef.hexe-ai.com",
            "Origin": "https://0123456789abcdef.hexe-ai.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "https://0123456789abcdef.hexe-ai.com"
    assert response.headers["access-control-allow-headers"] == "Authorization, Content-Type"
    assert response.headers["vary"] == "Origin"


def test_public_web_app_api_rejects_disallowed_origin():
    response = client().get(
        "/api/web-app/bootstrap",
        headers={"Host": "0123456789abcdef.hexe-ai.com", "Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "cors_origin_not_allowed"
    assert "access-control-allow-origin" not in response.headers


def test_public_web_app_api_response_allows_exact_core_origin():
    origin = "https://0123456789abcdef.hexe-ai.com"
    response = client().get(
        "/api/web-app/bootstrap",
        headers={"Host": "0123456789abcdef.hexe-ai.com", "Origin": origin},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["vary"] == "Origin"


def test_public_web_app_preflight_rejects_unlisted_header():
    response = client().options(
        "/api/web-app/bootstrap",
        headers={
            "Host": "0123456789abcdef.hexe-ai.com",
            "Origin": "https://0123456789abcdef.hexe-ai.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Admin-Token",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "cors_headers_not_allowed"


def test_development_origin_requires_explicit_development_mode():
    headers = {
        "Host": "0123456789abcdef.hexe-ai.com",
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization",
    }
    with patch.dict(os.environ, {"HEXE_ENABLE_DEV_CORS": "0"}, clear=False):
        assert client().options("/api/web-app/bootstrap", headers=headers).status_code == 403
    with patch.dict(os.environ, {"HEXE_ENABLE_DEV_CORS": "1"}, clear=False):
        response = client().options("/api/web-app/bootstrap", headers=headers)
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_local_web_app_path_keeps_same_origin_behavior():
    response = client().get(
        "/api/web-app/bootstrap",
        headers={"Host": "192.168.1.20:9001", "Origin": "http://192.168.1.20:9001"},
    )
    assert response.status_code == 200
    assert response.json() == {"path": "/api/web-app/bootstrap"}


def test_public_web_app_api_rejects_credentials_in_query_string():
    response = client().get(
        "/api/web-app/bootstrap?access_token=secret",
        headers={"Host": "0123456789abcdef.hexe-ai.com"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "credentials_in_query_forbidden"


def test_public_web_app_api_rejects_oversized_declared_body():
    response = client().request(
        "POST",
        "/api/web-app/bootstrap",
        headers={
            "Host": "0123456789abcdef.hexe-ai.com",
            "Content-Length": str(1024 * 1024 + 1),
        },
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "request_body_too_large"


def test_public_web_app_api_rate_limit_is_source_bounded():
    test_client = client(rate_limit_per_minute=2)
    headers = {"Host": "0123456789abcdef.hexe-ai.com"}
    assert test_client.get("/api/web-app/bootstrap", headers=headers).status_code == 200
    assert test_client.get("/api/web-app/bootstrap", headers=headers).status_code == 200
    limited = test_client.get("/api/web-app/bootstrap", headers=headers)
    assert limited.status_code == 429
    assert limited.json()["detail"] == "web_app_rate_limit_exceeded"
    assert limited.headers["retry-after"] == "60"


def test_local_web_app_api_is_not_subject_to_public_rate_limit():
    test_client = client(rate_limit_per_minute=1)
    headers = {"Host": "192.168.1.20:9001"}
    assert test_client.get("/api/web-app/bootstrap", headers=headers).status_code == 200
    assert test_client.get("/api/web-app/bootstrap", headers=headers).status_code == 200


def test_public_host_allows_only_explicit_anonymous_api_surface():
    public = {"Host": "0123456789abcdef.hexe-ai.com"}
    assert client().get("/api/auth/web-app/discovery", headers=public).status_code == 200
    assert client().get("/api/web-app/bootstrap", headers=public).status_code == 200
    blocked = client().get("/api/system/stats/current", headers=public)
    assert blocked.status_code == 404
    assert blocked.json()["detail"] == "not_found"
    assert client().post("/api/auth/token", headers=public).status_code == 404


def test_public_host_rejects_admin_token_header():
    response = client().get(
        "/api/system/stats/current",
        headers={
            "Host": "0123456789abcdef.hexe-ai.com",
            "X-Admin-Token": "must-stay-local",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "remote_admin_token_forbidden"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_authenticated_admin_cookie_retains_public_admin_api_surface():
    with patch.dict(os.environ, {"HEXE_ADMIN_TOKEN": "test-admin-token"}, clear=False):
        cookie, _ = _build_session_cookie(expected_token="test-admin-token", actor_id="admin-user")
        test_client = client()
        test_client.cookies.set("hexe_admin_session", cookie)
        response = test_client.get(
            "/api/system/stats/current",
            headers={"Host": "0123456789abcdef.hexe-ai.com"},
        )
    assert response.status_code == 200
    assert response.json() == {"path": "/api/system/stats/current"}


def test_local_host_keeps_existing_api_surface_and_admin_token_compatibility():
    response = client().get(
        "/api/system/stats/current",
        headers={"Host": "192.168.1.20:9001", "X-Admin-Token": "local-token"},
    )
    assert response.status_code == 200
    assert response.json() == {"path": "/api/system/stats/current"}


def test_public_login_and_refresh_share_source_rate_limit():
    test_client = client(sensitive_auth_rate_limit_per_minute=2)
    headers = {"Host": "0123456789abcdef.hexe-ai.com"}
    assert test_client.post("/api/auth/user/login", headers=headers).status_code == 405
    assert test_client.post("/api/auth/user/refresh", headers=headers).status_code == 405
    limited = test_client.post("/api/auth/user/login", headers=headers)
    assert limited.status_code == 429
    assert limited.json()["detail"] == "authentication_rate_limit_exceeded"
    assert limited.headers["retry-after"] == "60"


def test_public_enrollment_completion_is_source_rate_limited():
    test_client = client(sensitive_auth_rate_limit_per_minute=1)
    headers = {"Host": "0123456789abcdef.hexe-ai.com"}
    assert test_client.post("/api/auth/device-enrollments/enr-1/complete", headers=headers).status_code == 405
    limited = test_client.post("/api/auth/device-enrollments/enr-2/complete", headers=headers)
    assert limited.status_code == 429
    assert limited.json()["detail"] == "authentication_rate_limit_exceeded"


def test_local_login_is_not_subject_to_public_auth_rate_limit():
    test_client = client(sensitive_auth_rate_limit_per_minute=1)
    headers = {"Host": "192.168.1.20:9001"}
    assert test_client.post("/api/auth/user/login", headers=headers).status_code == 405
    assert test_client.post("/api/auth/user/login", headers=headers).status_code == 405
