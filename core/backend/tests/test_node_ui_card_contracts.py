import unittest

from app.nodes.ui_cards import (
    ActionPanelCardResponse,
    FactsCardResponse,
    HealthStripCardResponse,
    NodeOverviewCardResponse,
    NodeUiCardValidationError,
    ProviderStatusCardResponse,
    RecordListCardResponse,
    RuntimeServiceCardResponse,
    WarningBannerCardResponse,
    validate_node_ui_card_response,
)


UPDATED_AT = "2026-05-13T01:00:00Z"


class TestNodeUiCardContracts(unittest.TestCase):
    def test_node_overview_response_is_valid(self) -> None:
        response = NodeOverviewCardResponse.model_validate(
            {
                "kind": "node_overview",
                "updated_at": UPDATED_AT,
                "identity": [{"id": "node_id", "label": "Node ID", "value": "voice-node-1"}],
                "lifecycle": [{"id": "state", "label": "Lifecycle", "value": "operational", "tone": "success"}],
                "trust": [{"id": "trust", "label": "Trust", "value": "trusted", "tone": "success"}],
                "software": [{"id": "version", "label": "Version", "value": "0.1.0"}],
                "core_pairing": [{"id": "core", "label": "Core", "value": "paired", "tone": "success"}],
            }
        )
        self.assertEqual(response.kind, "node_overview")
        self.assertEqual(response.identity[0].value, "voice-node-1")

    def test_health_strip_response_is_valid(self) -> None:
        response = validate_node_ui_card_response(
            "health_strip",
            {
                "kind": "health_strip",
                "updated_at": UPDATED_AT,
                "items": [
                    {"state_name": "Lifecycle", "current_state": "operational", "tone": "success"},
                    {"state_name": "Trust", "current_state": "trusted", "tone": "success"},
                ],
            },
        )
        self.assertIsInstance(response, HealthStripCardResponse)

    def test_facts_card_response_is_valid(self) -> None:
        response = FactsCardResponse.model_validate(
            {
                "kind": "facts_card",
                "updated_at": UPDATED_AT,
                "title": "Live Status",
                "facts": [
                    {"id": "active_sessions", "label": "Active Sessions", "value": 2},
                    {"id": "latency", "label": "Latency", "value": 120, "unit": "ms", "tone": "info"},
                ],
            }
        )
        self.assertEqual(response.facts[1].unit, "ms")

    def test_warning_banner_response_is_valid(self) -> None:
        response = WarningBannerCardResponse.model_validate(
            {
                "kind": "warning_banner",
                "updated_at": UPDATED_AT,
                "warnings": [
                    {
                        "id": "provider_degraded",
                        "title": "Provider degraded",
                        "message": "Fallback provider is active.",
                        "tone": "warning",
                        "actions": [{"id": "refresh_provider", "label": "Refresh provider"}],
                    }
                ],
            }
        )
        self.assertEqual(response.warnings[0].actions[0].id, "refresh_provider")

    def test_action_panel_response_is_valid(self) -> None:
        response = ActionPanelCardResponse.model_validate(
            {
                "kind": "action_panel",
                "updated_at": UPDATED_AT,
                "groups": [
                    {
                        "id": "runtime",
                        "label": "Runtime",
                        "actions": [
                            {"id": "restart_service", "label": "Restart service", "enabled": True, "tone": "warning"},
                            {
                                "id": "stop_session",
                                "label": "Stop session",
                                "enabled": False,
                                "disabled_reason": "No active session",
                            },
                        ],
                    }
                ],
            }
        )
        self.assertFalse(response.groups[0].actions[1].enabled)
        self.assertEqual(response.groups[0].actions[1].disabled_reason, "No active session")

    def test_record_list_response_is_valid(self) -> None:
        response = validate_node_ui_card_response(
            "record_list",
            {
                "kind": "record_list",
                "updated_at": UPDATED_AT,
                "summary": {"record_count": 1},
                "columns": [{"id": "name", "label": "Name"}, {"id": "status", "label": "Status"}],
                "records": [
                    {
                        "id": "endpoint-1",
                        "name": "Endpoint 1",
                        "status": "online",
                        "tone": "success",
                        "endpoint_id": "endpoint-1",
                        "detail_ref": {"endpoint": "/api/endpoint/status/endpoint-1"},
                    }
                ],
            },
        )
        self.assertIsInstance(response, RecordListCardResponse)
        self.assertEqual(response.records[0].model_extra["endpoint_id"], "endpoint-1")

    def test_runtime_service_response_is_valid(self) -> None:
        response = RuntimeServiceCardResponse.model_validate(
            {
                "kind": "runtime_service",
                "updated_at": UPDATED_AT,
                "services": [
                    {
                        "id": "backend",
                        "label": "Backend",
                        "state": "running",
                        "tone": "success",
                        "healthy": True,
                        "provider": "systemd",
                        "model": "backend",
                        "resource_usage": {"process_cpu_percent": 1.5, "process_memory_rss_bytes": 1024},
                        "restart_supported": True,
                        "restart_target": "backend",
                        "runtime_state": "running",
                        "health_status": "success",
                        "facts": [{"id": "pid", "label": "PID", "value": 1234}],
                        "actions": [{"id": "restart_backend", "label": "Restart"}],
                    }
                ],
                "actions": [{"id": "refresh_runtime", "label": "Refresh Runtime"}],
                "supervisor": {"configured": True},
            }
        )
        self.assertEqual(response.services[0].runtime_state, "running")
        self.assertEqual(response.services[0].resource_usage["process_cpu_percent"], 1.5)
        self.assertEqual(response.actions[0].id, "refresh_runtime")

    def test_provider_status_response_is_valid(self) -> None:
        response = ProviderStatusCardResponse.model_validate(
            {
                "kind": "provider_status",
                "updated_at": UPDATED_AT,
                "providers": [
                    {
                        "id": "stt",
                        "label": "STT Provider",
                        "provider": "faster_whisper",
                        "state": "ready",
                        "tone": "success",
                        "facts": [{"id": "model", "label": "Model", "value": "small.en"}],
                        "setup": {
                            "facts": [{"id": "enabled", "label": "Enabled", "value": True}],
                            "errors": [],
                            "actions": [{"id": "save_provider_setup", "label": "Save Setup", "tone": "success"}],
                            "form": {
                                "title": "Provider Setup",
                                "submit_action_id": "save_provider_setup",
                                "fields": [
                                    {
                                        "id": "enabled_providers",
                                        "label": "Enabled Providers",
                                        "type": "multiselect",
                                        "value": ["voice"],
                                        "options": [
                                            {"value": "voice", "label": "Voice"},
                                            {"value": "piper", "label": "Piper"},
                                        ],
                                        "required": True,
                                    },
                                    {
                                        "id": "default_provider",
                                        "label": "Default Provider",
                                        "type": "select",
                                        "value": "voice",
                                        "options": [{"value": "voice", "label": "Voice"}],
                                    },
                                ],
                            },
                        },
                    }
                ],
            }
        )
        self.assertEqual(response.providers[0].provider, "faster_whisper")
        self.assertEqual(response.providers[0].setup.facts[0].id, "enabled")
        self.assertEqual(response.providers[0].setup.form.submit_action_id, "save_provider_setup")
        self.assertEqual(response.providers[0].setup.form.fields[0].type, "multiselect")

    def test_rejects_secret_keys_in_payload(self) -> None:
        with self.assertRaises(ValueError):
            FactsCardResponse.model_validate(
                {
                    "kind": "facts_card",
                    "updated_at": UPDATED_AT,
                    "facts": [{"id": "api", "label": "API", "value": "ok"}],
                    "data": {"api_key": "should-not-appear"},
                }
            )

    def test_rejects_unsafe_text(self) -> None:
        with self.assertRaises(ValueError):
            HealthStripCardResponse.model_validate(
                {
                    "kind": "health_strip",
                    "updated_at": UPDATED_AT,
                    "items": [{"state_name": "<script>x</script>", "current_state": "bad", "tone": "error"}],
                }
            )

    def test_rejects_unsupported_kind_for_dispatch_validation(self) -> None:
        with self.assertRaises(NodeUiCardValidationError):
            validate_node_ui_card_response("future_card", {"kind": "future_card", "updated_at": UPDATED_AT})


if __name__ == "__main__":
    unittest.main()
