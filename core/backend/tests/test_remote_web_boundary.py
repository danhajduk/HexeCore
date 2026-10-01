from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.remote_web_boundary import RemoteWebBoundaryMiddleware


class Settings:
    def __init__(self):
        self.data = {"platform.core_id": "0123456789abcdef", "platform.domain": "hexe-ai.com"}

    async def get_all(self):
        return dict(self.data)

    async def set(self, key, value):
        self.data[key] = value


def client():
    app = FastAPI()
    app.state.settings_store = Settings()
    app.add_middleware(RemoteWebBoundaryMiddleware)

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
