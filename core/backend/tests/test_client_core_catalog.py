from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.system.client_catalog import build_client_core_catalog_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(build_client_core_catalog_router(), prefix="/api")
    return TestClient(app)


def test_client_core_catalog_reports_current_and_proposed_security_separately() -> None:
    response = _client().get("/api/schemas/client-core/v1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_family"] == "client-core"
    assert payload["version"] == "v1"

    api_paths = {item["api_path"]: item for item in payload["apis"]}
    assert api_paths["/api/system/nodes/services/resolve"]["status"] == "Implemented"
    assert api_paths["/api/system/nodes/services/authorize"]["status"] == "Implemented"
    assert "/api/system/nodes/services/introspect" not in api_paths

    proposals = {item["name"]: item for item in payload["security_proposals"]}
    introspection = proposals["provider_service_token_introspection"]
    assert introspection["status"] == "Not implemented"
    assert introspection["proposed_api_path"] == "/api/system/nodes/services/introspect"
    assert payload["current_security"]["provider_token_verification"].startswith("Not implemented")


def test_client_core_catalog_publishes_schema_and_documents() -> None:
    client = _client()

    schema = client.get("/api/schemas/client-core/v1/schema-catalog.v1.response.schema.json")
    assert schema.status_code == 200
    assert schema.json()["title"] == "ClientCoreCatalogResponse"

    readme = client.get("/api/schemas/client-core/v1/README.md")
    assert readme.status_code == 200
    assert readme.headers["content-type"].startswith("text/plain")
    assert "provider-side service-token introspection is **not implemented**" in readme.text.lower()

    proposal = client.get("/api/schemas/client-core/v1/service-token-introspection-proposal.md")
    assert proposal.status_code == 200
    assert "Status: Not implemented" in proposal.text
    assert "X-Node-Id" in proposal.text
    assert "maximum token" in proposal.text
