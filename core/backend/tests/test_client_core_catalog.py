from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.system.client_catalog import build_client_core_catalog_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(build_client_core_catalog_router(), prefix="/api")
    return TestClient(app)


def test_client_core_catalog_reports_implemented_core_security_and_provider_adoption() -> None:
    response = _client().get("/api/schemas/client-core/v1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_family"] == "client-core"
    assert payload["version"] == "v1"

    api_paths = {item["api_path"]: item for item in payload["apis"]}
    assert api_paths["/api/system/nodes/services/resolve"]["status"] == "Implemented"
    assert api_paths["/api/system/nodes/services/authorize"]["status"] == "Implemented"
    assert api_paths["/api/system/nodes/services/introspect"]["status"] == "Implemented"
    grant_entries = [item for item in payload["apis"] if item["name"].startswith("service_access_grant_")]
    assert {(item["method"], item["api_path"]) for item in grant_entries} == {
        ("GET", "/api/system/nodes/service-access/grants"),
        ("POST", "/api/system/nodes/service-access/grants"),
        ("GET", "/api/system/nodes/service-access/grants/{grant_id}"),
        ("PUT", "/api/system/nodes/service-access/grants/{grant_id}"),
        ("POST", "/api/system/nodes/service-access/grants/{grant_id}/revoke"),
    }

    proposals = {item["name"]: item for item in payload["security_proposals"]}
    introspection = proposals["provider_service_token_introspection"]
    assert introspection["status"] == "Implemented"
    assert introspection["proposed_api_path"] == "/api/system/nodes/services/introspect"
    assert payload["current_security"]["provider_token_verification"].startswith("Implemented")
    assert proposals["universal_resolved_service_enforcement"]["status"] == "Partially implemented"
    assert proposals["governed_privileged_scope_issuance"]["status"] == "Implemented"
    assert proposals["lifetime_based_rotation_retention"]["status"] == "Implemented"


def test_client_core_catalog_publishes_schema_and_documents() -> None:
    client = _client()

    schema = client.get("/api/schemas/client-core/v1/schema-catalog.v1.response.schema.json")
    assert schema.status_code == 200
    assert schema.json()["title"] == "ClientCoreCatalogResponse"

    readme = client.get("/api/schemas/client-core/v1/README.md")
    assert readme.status_code == 200
    assert readme.headers["content-type"].startswith("text/plain")
    assert "service-token introspection" in readme.text.lower()
    assert "implemented" in readme.text.lower()

    contract = client.get("/api/schemas/client-core/v1/service-token-security-contract.md")
    assert contract.status_code == 200
    assert "Status: Implemented" in contract.text
    assert "X-Node-Id" in contract.text
    assert "latest token expiration" in contract.text
