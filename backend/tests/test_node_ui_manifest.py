import unittest

from app.nodes.ui_manifest import (
    NODE_UI_MANIFEST_SCHEMA_VERSION,
    NodeUiManifestValidationError,
    validate_node_ui_manifest,
)


class TestNodeUiManifest(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "schema_version": NODE_UI_MANIFEST_SCHEMA_VERSION,
            "manifest_revision": "rev-1",
            "node_id": "voice-node-1",
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
                            "title": "Node Health",
                            "data_endpoint": "/api/node/ui/overview/health",
                            "refresh": {"mode": "near_live", "interval_ms": 15000},
                        },
                        {
                            "id": "node.actions",
                            "kind": "action_panel",
                            "title": "Actions",
                            "data_endpoint": "/api/node/ui/overview/actions",
                            "actions": [
                                {
                                    "id": "restart_service",
                                    "label": "Restart service",
                                    "method": "POST",
                                    "endpoint": "/api/services/restart",
                                    "destructive": True,
                                    "confirmation": {
                                        "required": True,
                                        "title": "Restart service?",
                                        "message": "This may interrupt active work.",
                                        "tone": "danger",
                                    },
                                }
                            ],
                            "refresh": {"mode": "manual", "cache_ttl_ms": 10000},
                        },
                    ],
                },
                {
                    "id": "voice.intents",
                    "title": "Intents",
                    "surfaces": [
                        {
                            "id": "voice.intent_registry",
                            "kind": "record_list",
                            "title": "Registered Intents",
                            "data_endpoint": "/api/node/ui/voice/intents",
                            "detail_endpoint_template": "/api/voice/intents/{intent_id}",
                            "refresh": {"mode": "manual"},
                        }
                    ],
                },
            ],
        }

    def test_valid_manifest_is_accepted(self) -> None:
        manifest = validate_node_ui_manifest(self._payload())

        self.assertEqual(manifest.schema_version, "1.0")
        self.assertEqual(manifest.node_id, "voice-node-1")
        self.assertEqual(manifest.pages[0].surfaces[0].refresh.interval_ms, 15000)
        self.assertEqual(manifest.pages[0].surfaces[1].actions[0].method, "POST")

    def test_rejects_unknown_top_level_keys(self) -> None:
        payload = self._payload()
        payload["html"] = "<div></div>"
        with self.assertRaises(NodeUiManifestValidationError):
            validate_node_ui_manifest(payload)

    def test_rejects_executable_text(self) -> None:
        payload = self._payload()
        payload["pages"][0]["surfaces"][0]["title"] = "<script>alert(1)</script>"
        with self.assertRaises(NodeUiManifestValidationError):
            validate_node_ui_manifest(payload)

    def test_rejects_unsupported_schema_version(self) -> None:
        payload = self._payload()
        payload["schema_version"] = "2.0"
        with self.assertRaises(NodeUiManifestValidationError):
            validate_node_ui_manifest(payload)

    def test_rejects_absolute_or_invalid_endpoints(self) -> None:
        payload = self._payload()
        payload["pages"][0]["surfaces"][0]["data_endpoint"] = "http://node.local/api/node/ui/overview/health"
        with self.assertRaises(NodeUiManifestValidationError):
            validate_node_ui_manifest(payload)

    def test_rejects_duplicate_surface_ids(self) -> None:
        payload = self._payload()
        payload["pages"][1]["surfaces"][0]["id"] = "node.health"
        with self.assertRaises(NodeUiManifestValidationError):
            validate_node_ui_manifest(payload)

    def test_rejects_sensitive_action_without_confirmation(self) -> None:
        payload = self._payload()
        action = payload["pages"][0]["surfaces"][1]["actions"][0]
        action.pop("confirmation")
        with self.assertRaises(NodeUiManifestValidationError):
            validate_node_ui_manifest(payload)

    def test_rejects_polling_refresh_without_valid_interval(self) -> None:
        payload = self._payload()
        payload["pages"][0]["surfaces"][0]["refresh"]["interval_ms"] = 500
        with self.assertRaises(NodeUiManifestValidationError):
            validate_node_ui_manifest(payload)

    def test_allows_unknown_but_safe_card_kind(self) -> None:
        payload = self._payload()
        payload["pages"][0]["surfaces"][0]["kind"] = "future_card"
        manifest = validate_node_ui_manifest(payload)
        self.assertEqual(manifest.pages[0].surfaces[0].kind, "future_card")

    def test_allows_page_endpoint_with_page_refresh(self) -> None:
        payload = self._payload()
        payload["pages"][0].pop("surfaces")
        payload["pages"][0]["page_endpoint"] = "/api/node/ui/pages/overview"
        payload["pages"][0]["refresh"] = {"mode": "near_live", "interval_ms": 15000}

        manifest = validate_node_ui_manifest(payload)

        self.assertEqual(manifest.pages[0].page_endpoint, "/api/node/ui/pages/overview")
        self.assertEqual(manifest.pages[0].refresh.interval_ms, 15000)
        self.assertEqual(manifest.pages[0].surfaces, [])

    def test_rejects_empty_page_without_page_endpoint(self) -> None:
        payload = self._payload()
        payload["pages"][0]["surfaces"] = []
        with self.assertRaises(NodeUiManifestValidationError):
            validate_node_ui_manifest(payload)

    def test_requires_refresh_when_page_endpoint_is_used(self) -> None:
        payload = self._payload()
        payload["pages"][0].pop("surfaces")
        payload["pages"][0]["page_endpoint"] = "/api/node/ui/pages/overview"
        with self.assertRaises(NodeUiManifestValidationError):
            validate_node_ui_manifest(payload)


if __name__ == "__main__":
    unittest.main()
