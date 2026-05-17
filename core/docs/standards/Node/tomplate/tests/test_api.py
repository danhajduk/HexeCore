from fastapi.testclient import TestClient

from node_template.main import create_app


def test_status_endpoint():
    client = TestClient(create_app())
    response = client.get("/api/node/status")
    assert response.status_code == 200
    assert response.json()["trust_state"] == "untrusted"
