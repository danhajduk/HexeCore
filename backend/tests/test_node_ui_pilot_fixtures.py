from __future__ import annotations

import unittest

import httpx

from app.nodes import NodeRecord, NodeUiManifestFetchService, validate_node_ui_card_response, validate_node_ui_manifest
from tests.fixtures.node_ui_pilot import pilot_node_ui_card_responses, pilot_node_ui_manifest


class _FakeNodesService:
    def get_node(self, node_id: str) -> NodeRecord:
        return NodeRecord.model_validate(
            {
                "node_id": node_id,
                "node_name": "pilot-node",
                "node_type": "voice",
                "node_software_version": "1.0.0",
                "api_base_url": "http://pilot-node.local:8081/api",
                "status": {"trust_status": "trusted", "registry_state": "trusted"},
            }
        )


class TestNodeUiPilotFixtures(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        client = getattr(self, "client", None)
        if client is not None:
            await client.aclose()

    def test_pilot_manifest_and_card_payloads_match_core_contracts(self) -> None:
        manifest = validate_node_ui_manifest(pilot_node_ui_manifest())
        responses = pilot_node_ui_card_responses()

        surface_kinds = {surface.kind for page in manifest.pages for surface in page.surfaces}

        self.assertEqual(surface_kinds, set(responses))
        for kind, payload in responses.items():
            validated = validate_node_ui_card_response(kind, payload)
            self.assertEqual(validated.kind, kind)

    async def test_manifest_fetch_service_accepts_pilot_manifest(self) -> None:
        seen_urls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_urls.append(str(request.url))
            return httpx.Response(200, json=pilot_node_ui_manifest())

        self.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
        service = NodeUiManifestFetchService(_FakeNodesService(), client=self.client)

        response = await service.fetch_manifest("pilot-node-1")

        self.assertTrue(response.ok)
        self.assertEqual(response.manifest_revision, "pilot-rev-1")
        self.assertEqual(seen_urls, ["http://pilot-node.local:8081/api/node/ui-manifest"])
        self.assertIsNotNone(service.cached_manifest("pilot-node-1", "pilot-rev-1"))
