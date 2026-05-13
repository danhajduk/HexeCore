from __future__ import annotations

import os
import unittest

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.nodes import NodeRecord, NodeUiManifestFetchResponse, NodeUiManifestFetchService, build_nodes_router


def _manifest(*, revision: str | None = "rev-1") -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "node_id": "node-1",
        "node_type": "voice",
        "display_name": "Voice Node",
        "pages": [
            {
                "id": "overview",
                "title": "Overview",
                "surfaces": [
                    {
                        "id": "node.health",
                        "kind": "health_strip",
                        "title": "Health",
                        "data_endpoint": "/api/node/ui/overview/health",
                        "refresh": {"mode": "near_live", "interval_ms": 15000},
                    }
                ],
            }
        ],
    }
    if revision is not None:
        payload["manifest_revision"] = revision
    return payload


def _node(**overrides: object) -> NodeRecord:
    payload: dict[str, object] = {
        "node_id": "node-1",
        "node_name": "voice-node",
        "node_type": "voice",
        "node_software_version": "1.0.0",
        "api_base_url": "http://node.local:8081/api",
        "status": {"trust_status": "trusted", "registry_state": "trusted"},
    }
    payload.update(overrides)
    return NodeRecord.model_validate(payload)


class _FakeNodesService:
    def __init__(self, node: NodeRecord | None = None) -> None:
        self.node = node or _node()

    def get_node(self, node_id: str) -> NodeRecord:
        if node_id != self.node.node_id:
            raise HTTPException(status_code=404, detail="node_not_found")
        return self.node


class TestNodeUiManifestFetchService(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        client = getattr(self, "client", None)
        if client is not None:
            await client.aclose()

    def _service(self, handler) -> NodeUiManifestFetchService:
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
        return NodeUiManifestFetchService(_FakeNodesService(), client=self.client)

    async def test_fetches_and_validates_manifest_from_node_api_base(self) -> None:
        seen_urls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_urls.append(str(request.url))
            return httpx.Response(200, json=_manifest())

        service = self._service(handler)

        response = await service.fetch_manifest("node-1")

        self.assertTrue(response.ok)
        self.assertEqual(response.status, "available")
        self.assertEqual(response.manifest_revision, "rev-1")
        self.assertEqual(response.manifest["display_name"], "Voice Node")
        self.assertEqual(seen_urls, ["http://node.local:8081/api/node/ui-manifest"])
        self.assertIsNotNone(service.cached_manifest("node-1", "rev-1"))

    async def test_derives_api_base_without_requiring_node_hosted_ui(self) -> None:
        seen_urls: list[str] = []
        node = _node(api_base_url=None, ui_enabled=False, requested_hostname="node-host.local:8081")

        def handler(request: httpx.Request) -> httpx.Response:
            seen_urls.append(str(request.url))
            return httpx.Response(200, json=_manifest())

        self.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
        service = NodeUiManifestFetchService(_FakeNodesService(node), client=self.client)

        response = await service.fetch_manifest("node-1")

        self.assertTrue(response.ok)
        self.assertEqual(seen_urls, ["http://node-host.local:8081/api/node/ui-manifest"])

    async def test_returns_endpoint_not_configured_when_no_api_base_can_be_derived(self) -> None:
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
        service = NodeUiManifestFetchService(_FakeNodesService(_node(api_base_url=None)), client=self.client)

        response = await service.fetch_manifest("node-1")

        self.assertFalse(response.ok)
        self.assertEqual(response.status, "endpoint_not_configured")
        self.assertEqual(response.error_code, "node_api_endpoint_not_configured")

    async def test_returns_not_trusted_before_fetching_manifest(self) -> None:
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
        service = NodeUiManifestFetchService(
            _FakeNodesService(_node(status={"trust_status": "approved", "registry_state": "approved"})),
            client=self.client,
        )

        response = await service.fetch_manifest("node-1")

        self.assertFalse(response.ok)
        self.assertEqual(response.status, "node_not_trusted")
        self.assertEqual(response.error_code, "node_not_trusted")

    async def test_returns_fetch_failed_for_node_http_error(self) -> None:
        service = self._service(lambda request: httpx.Response(503, json={"error": "warming"}))

        response = await service.fetch_manifest("node-1")

        self.assertFalse(response.ok)
        self.assertEqual(response.status, "fetch_failed")
        self.assertEqual(response.error_code, "node_manifest_http_error")
        self.assertIn("HTTP 503", response.detail)

    async def test_returns_invalid_manifest_for_non_object_payload(self) -> None:
        service = self._service(lambda request: httpx.Response(200, json=[]))

        response = await service.fetch_manifest("node-1")

        self.assertFalse(response.ok)
        self.assertEqual(response.status, "invalid_manifest")
        self.assertEqual(response.error_code, "node_manifest_not_object")

    async def test_returns_invalid_manifest_for_contract_failure(self) -> None:
        invalid = _manifest()
        invalid["pages"] = []
        service = self._service(lambda request: httpx.Response(200, json=invalid))

        response = await service.fetch_manifest("node-1")

        self.assertFalse(response.ok)
        self.assertEqual(response.status, "invalid_manifest")
        self.assertEqual(response.error_code, "manifest_validation_failed")

    async def test_reports_latest_cached_manifest_revision_on_failure(self) -> None:
        responses = [httpx.Response(200, json=_manifest(revision="rev-2")), httpx.Response(503)]

        def handler(request: httpx.Request) -> httpx.Response:
            return responses.pop(0)

        service = self._service(handler)

        first = await service.fetch_manifest("node-1")
        second = await service.fetch_manifest("node-1")

        self.assertTrue(first.ok)
        self.assertFalse(second.ok)
        self.assertEqual(second.cached_manifest_revision, "rev-2")

    async def test_returns_node_not_found_as_failure_state(self) -> None:
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
        service = NodeUiManifestFetchService(_FakeNodesService(), client=self.client)

        response = await service.fetch_manifest("missing")

        self.assertFalse(response.ok)
        self.assertEqual(response.status, "node_not_found")
        self.assertEqual(response.error_code, "node_not_found")


class _FakeManifestService:
    async def fetch_manifest(self, node_id: str) -> NodeUiManifestFetchResponse:
        return NodeUiManifestFetchResponse(
            node_id=node_id,
            ok=True,
            status="available",
            manifest=_manifest(),
            manifest_revision="rev-1",
        )


class TestNodeUiManifestRoute(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["SYNTHIA_ADMIN_TOKEN"] = "test-token"
        app = FastAPI()
        app.include_router(build_nodes_router(_FakeNodesService(), _FakeManifestService()), prefix="/api")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        os.environ.pop("SYNTHIA_ADMIN_TOKEN", None)

    def test_route_requires_admin_auth(self) -> None:
        response = self.client.get("/api/nodes/node-1/ui-manifest")

        self.assertEqual(response.status_code, 401, response.text)

    def test_route_returns_manifest_fetch_response(self) -> None:
        response = self.client.get("/api/nodes/node-1/ui-manifest", headers={"X-Admin-Token": "test-token"})

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "available")
        self.assertEqual(payload["manifest_revision"], "rev-1")
