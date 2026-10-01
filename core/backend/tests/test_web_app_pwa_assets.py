import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "frontend"


def test_manifest_opens_mobile_assistant_surface():
    manifest = json.loads((ROOT / "public" / "site.webmanifest").read_text())
    assert manifest["start_url"] == "/app"
    assert manifest["display"] == "standalone"
    assert {icon["sizes"] for icon in manifest["icons"]} >= {"192x192", "512x512"}


def test_service_worker_never_caches_authenticated_api_requests():
    worker = (ROOT / "public" / "service-worker.js").read_text()
    assert 'startsWith("/api/")' in worker
    assert 'caches.match("/offline.html")' in worker
    assert 'caches.delete(key)' in worker
