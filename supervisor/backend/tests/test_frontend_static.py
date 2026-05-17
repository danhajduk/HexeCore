from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from app.frontend_static import build_frontend_static_router


def _write_dist(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>Hexe</title><div id=\"root\"></div>", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "main.js").write_text("console.log('hexe')", encoding="utf-8")


def _client(dist: Path) -> TestClient:
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/nodes/proxy/ui/{node_id}/{path:path}")
    async def node_proxy(node_id: str, path: str):
        return PlainTextResponse(f"node:{node_id}:{path}")

    @app.get("/addons/proxy/{addon_id}/{path:path}")
    async def addon_proxy(addon_id: str, path: str):
        return PlainTextResponse(f"addon:{addon_id}:{path}")

    router = build_frontend_static_router(dist)
    assert router is not None
    app.include_router(router)
    return TestClient(app)


def test_serves_static_assets_and_spa_routes(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write_dist(dist)
    client = _client(dist)

    root = client.get("/")
    assert root.status_code == 200
    assert "<title>Hexe</title>" in root.text

    asset = client.get("/assets/main.js")
    assert asset.status_code == 200
    assert "console.log" in asset.text

    nested = client.get("/settings/jobs")
    assert nested.status_code == 200
    assert "<title>Hexe</title>" in nested.text


def test_reserved_backend_routes_are_not_shadowed_by_spa_fallback(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write_dist(dist)
    client = _client(dist)

    api = client.get("/api/health")
    assert api.status_code == 200
    assert api.json() == {"status": "ok"}

    missing_api = client.get("/api/missing")
    assert missing_api.status_code == 404

    node = client.get("/nodes/proxy/ui/node-1/status")
    assert node.status_code == 200
    assert node.text == "node:node-1:status"

    addon = client.get("/addons/proxy/mqtt/assets/main.js")
    assert addon.status_code == 200
    assert addon.text == "addon:mqtt:assets/main.js"

    missing_node_proxy = client.get("/nodes/proxy/missing")
    assert missing_node_proxy.status_code == 404


def test_missing_static_asset_returns_404_not_index(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write_dist(dist)
    client = _client(dist)

    response = client.get("/assets/missing.js")
    assert response.status_code == 404
    assert "<title>Hexe</title>" not in response.text
