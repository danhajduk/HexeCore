import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from app.nodes.models_resolution import TaskExecutionResolutionRequest
from app.system.onboarding.registrations import NodeRegistrationsStore
from app.system.services.node_resolution import NodeServiceResolutionService


class _EmptyCatalogStore:
    async def all_catalogs(self) -> dict:
        return {}


class _PermissiveBudgetService:
    def effective_budget_view(
        self,
        *,
        node_id: str,
        task_family: str,
        provider: str | None = None,
        model_id: str | None = None,
    ) -> dict:
        return {
            "status": "active",
            "budget_node_id": node_id,
            "grant_id": f"grant:{node_id}:node",
            "provider": provider,
            "task_family": task_family,
            "model_id": model_id,
            "grant_scope_kind": "node",
            "admissible": True,
        }


class TestNodeServiceResolutionStoreCompat(unittest.TestCase):
    def test_resolution_uses_legacy_persisted_provider_capabilities_after_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "node_registrations.json"
            payload = {
                "schema_version": "3",
                "items": [
                    {
                        "node_id": "node-ai-legacy",
                        "node_type": "ai-node",
                        "node_name": "legacy-ai",
                        "node_software_version": "0.9.0",
                        "trust_status": "trusted",
                        "requested_api_base_url": "http://127.0.0.1:9000/api",
                        "declared_task_families": ["task.chat"],
                        "enabled_providers": ["openai"],
                        "provider_intelligence": [
                            {
                                "provider": "openai",
                                "available_models": [{"model_id": "gpt-4o-mini"}],
                            }
                        ],
                        "created_at": "2026-03-11T00:00:00+00:00",
                        "updated_at": "2026-03-11T00:00:00+00:00",
                    }
                ],
                "session_to_node": {},
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            registrations = NodeRegistrationsStore(path=path)
            service = NodeServiceResolutionService(_EmptyCatalogStore(), node_registrations_store=registrations)

            resolved = asyncio.run(
                service.resolve_for_node(
                    request=TaskExecutionResolutionRequest(
                        node_id="node-voice",
                        task_family="task.chat",
                        preferred_provider="openai",
                        preferred_model="gpt-4o-mini",
                    ),
                    governance_bundle={
                        "routing_policy_constraints": {
                            "allowed_task_families": ["task.chat"],
                            "allowed_providers": ["openai"],
                            "allowed_models": {"openai": ["gpt-4o-mini"]},
                        }
                    },
                    budget_service=_PermissiveBudgetService(),
                )
            )

            self.assertEqual(resolved.selected_service_id, "node-service:node-ai-legacy:openai")
            self.assertEqual(len(resolved.candidates), 1)
            candidate = resolved.candidates[0]
            self.assertEqual(candidate.provider_node_id, "node-ai-legacy")
            self.assertEqual(candidate.provider_api_base_url, "http://127.0.0.1:9000/api")
            self.assertEqual(candidate.models_allowed, ["gpt-4o-mini"])
            self.assertEqual(candidate.budget_view.budget_node_id, "node-ai-legacy")  # type: ignore[union-attr]

    def test_resolution_does_not_treat_requester_only_records_as_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "node_registrations.json"
            payload = {
                "schema_version": "4",
                "items": [
                    {
                        "node_id": "node-voice",
                        "node_type": "voice-node",
                        "node_name": "voice",
                        "node_software_version": "0.9.0",
                        "trust_status": "trusted",
                        "declared_capabilities": [],
                        "provided_task_families": [],
                        "requested_task_families": ["task.chat"],
                        "enabled_providers": ["openai"],
                        "created_at": "2026-03-11T00:00:00+00:00",
                        "updated_at": "2026-03-11T00:00:00+00:00",
                    }
                ],
                "session_to_node": {},
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            registrations = NodeRegistrationsStore(path=path)
            service = NodeServiceResolutionService(_EmptyCatalogStore(), node_registrations_store=registrations)

            resolved = asyncio.run(
                service.resolve_for_node(
                    request=TaskExecutionResolutionRequest(node_id="node-voice", task_family="task.chat"),
                    governance_bundle={"routing_policy_constraints": {"allowed_task_families": ["task.chat"]}},
                    budget_service=_PermissiveBudgetService(),
                )
            )

            self.assertEqual(resolved.candidates, [])

    def test_resolution_prefers_endpoint_provider_ids_over_node_enabled_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "node_registrations.json"
            payload = {
                "schema_version": "4",
                "items": [
                    {
                        "node_id": "node-voice",
                        "node_type": "voice-node",
                        "node_name": "voice",
                        "node_software_version": "0.9.0",
                        "trust_status": "trusted",
                        "provided_task_families": ["task.voice.tts.synthesize"],
                        "capability_endpoints": {
                            "task.voice.tts.synthesize": {
                                "method": "POST",
                                "path": "/api/tts/synthesize",
                                "url": "http://127.0.0.1:9004/api/tts/synthesize",
                                "provider_ids": ["piper"],
                            }
                        },
                        "enabled_providers": ["voice", "openwakeword", "piper"],
                        "created_at": "2026-03-11T00:00:00+00:00",
                        "updated_at": "2026-03-11T00:00:00+00:00",
                    }
                ],
                "session_to_node": {},
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            registrations = NodeRegistrationsStore(path=path)
            service = NodeServiceResolutionService(_EmptyCatalogStore(), node_registrations_store=registrations)

            resolved = asyncio.run(
                service.resolve_for_node(
                    request=TaskExecutionResolutionRequest(node_id="node-interaction", task_family="task.voice.tts.synthesize"),
                    governance_bundle={"routing_policy_constraints": {"allowed_task_families": ["task.voice.tts.synthesize"]}},
                    budget_service=_PermissiveBudgetService(),
                )
            )

            self.assertEqual(resolved.selected_service_id, "node-service:node-voice:piper")
            self.assertEqual([candidate.provider for candidate in resolved.candidates], ["piper"])
            self.assertEqual(resolved.candidates[0].execution_endpoint_url, "http://127.0.0.1:9004/api/tts/synthesize")

    def test_resolution_preserves_assistant_service_identity_and_operation_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "node_registrations.json"
            capability = "interaction.assistant.turn"
            service_id = f"node-service:node-interaction:{capability}"
            payload = {
                "schema_version": "4",
                "items": [
                    {
                        "node_id": "node-interaction",
                        "node_type": "interaction-node",
                        "node_name": "interaction",
                        "node_software_version": "1.0.0",
                        "trust_status": "trusted",
                        "requested_api_base_url": "http://127.0.0.1:9003",
                        "provided_task_families": [capability],
                        "capability_endpoints": {
                            capability: {
                                "service_id": service_id,
                                "audience": service_id,
                                "url": "http://127.0.0.1:9003/api/interaction/assistant/v1/turns",
                                "operations": {
                                    "submit": {"scope": "assistant.turn.submit"},
                                    "cancel": {"scope": "assistant.turn.cancel"},
                                    "resume": {"scope": "assistant.turn.resume"},
                                },
                            }
                        },
                        "enabled_providers": [],
                        "created_at": "2026-10-06T00:00:00+00:00",
                        "updated_at": "2026-10-06T00:00:00+00:00",
                    }
                ],
                "session_to_node": {},
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            registrations = NodeRegistrationsStore(path=path)
            service = NodeServiceResolutionService(_EmptyCatalogStore(), node_registrations_store=registrations)

            resolved = asyncio.run(
                service.resolve_for_node(
                    request=TaskExecutionResolutionRequest(node_id="node-voice", task_family=capability),
                    governance_bundle={"routing_policy_constraints": {"allowed_task_families": [capability]}},
                    budget_service=_PermissiveBudgetService(),
                )
            )

            self.assertEqual(resolved.selected_service_id, service_id)
            self.assertEqual(len(resolved.candidates), 1)
            candidate = resolved.candidates[0]
            self.assertEqual(candidate.provider_node_id, "node-interaction")
            self.assertEqual(
                candidate.required_scopes,
                ["assistant.turn.submit", "assistant.turn.cancel", "assistant.turn.resume"],
            )


if __name__ == "__main__":
    unittest.main()
