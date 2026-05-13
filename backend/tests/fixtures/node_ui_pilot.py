from __future__ import annotations


PILOT_UPDATED_AT = "2026-05-13T01:00:00Z"


def pilot_node_ui_manifest() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "manifest_revision": "pilot-rev-1",
        "node_id": "pilot-node-1",
        "node_type": "voice",
        "display_name": "Pilot Voice Node",
        "pages": [
            {
                "id": "overview",
                "title": "Overview",
                "surfaces": [
                    {
                        "id": "node.overview",
                        "kind": "node_overview",
                        "title": "Node Overview",
                        "data_endpoint": "/api/node/ui/overview",
                        "refresh": {"mode": "manual"},
                    },
                    {
                        "id": "node.health",
                        "kind": "health_strip",
                        "title": "Health",
                        "data_endpoint": "/api/node/ui/overview/health",
                        "refresh": {"mode": "near_live", "interval_ms": 15000},
                    },
                    {
                        "id": "node.warnings",
                        "kind": "warning_banner",
                        "title": "Warnings",
                        "data_endpoint": "/api/node/ui/overview/warnings",
                        "refresh": {"mode": "manual"},
                    },
                ],
            },
            {
                "id": "runtime",
                "title": "Runtime",
                "surfaces": [
                    {
                        "id": "runtime.services",
                        "kind": "runtime_service",
                        "title": "Services",
                        "data_endpoint": "/api/node/ui/runtime/services",
                        "actions": [
                            {
                                "id": "restart_backend",
                                "label": "Restart backend",
                                "method": "POST",
                                "endpoint": "/api/node/ui/runtime/services/backend/restart",
                                "destructive": True,
                                "confirmation": {
                                    "required": True,
                                    "message": "Restart backend service?",
                                    "tone": "warning",
                                },
                            }
                        ],
                        "refresh": {"mode": "manual"},
                    },
                    {
                        "id": "runtime.actions",
                        "kind": "action_panel",
                        "title": "Runtime Actions",
                        "data_endpoint": "/api/node/ui/runtime/actions",
                        "actions": [
                            {
                                "id": "clear_cache",
                                "label": "Clear cache",
                                "method": "DELETE",
                                "endpoint": "/api/node/ui/runtime/cache",
                                "sensitive": True,
                                "confirmation": {
                                    "required": True,
                                    "message": "Clear runtime cache?",
                                    "tone": "warning",
                                },
                            }
                        ],
                        "refresh": {"mode": "manual"},
                    },
                ],
            },
            {
                "id": "providers",
                "title": "Providers",
                "surfaces": [
                    {
                        "id": "providers.status",
                        "kind": "provider_status",
                        "title": "Providers",
                        "data_endpoint": "/api/node/ui/providers/status",
                        "refresh": {"mode": "near_live", "interval_ms": 30000},
                    },
                    {
                        "id": "providers.facts",
                        "kind": "facts_card",
                        "title": "Provider Facts",
                        "data_endpoint": "/api/node/ui/providers/facts",
                        "refresh": {"mode": "static"},
                    },
                ],
            },
        ],
    }


def pilot_node_ui_card_responses() -> dict[str, dict[str, object]]:
    return {
        "node_overview": {
            "kind": "node_overview",
            "updated_at": PILOT_UPDATED_AT,
            "identity": [{"id": "node_id", "label": "Node ID", "value": "pilot-node-1"}],
            "lifecycle": [{"id": "runtime", "label": "Runtime", "value": "running", "tone": "success"}],
            "trust": [{"id": "trust", "label": "Trust", "value": "trusted", "tone": "success"}],
            "software": [{"id": "version", "label": "Version", "value": "1.0.0"}],
            "core_pairing": [{"id": "core", "label": "Core", "value": "paired", "tone": "success"}],
        },
        "health_strip": {
            "kind": "health_strip",
            "updated_at": PILOT_UPDATED_AT,
            "items": [
                {"id": "lifecycle", "label": "Lifecycle", "value": "running", "tone": "success"},
                {"id": "providers", "label": "Providers", "value": "ready", "tone": "success"},
            ],
        },
        "warning_banner": {
            "kind": "warning_banner",
            "updated_at": PILOT_UPDATED_AT,
            "warnings": [
                {"id": "governance", "title": "Governance refresh due", "tone": "warning", "message": "Policy is near expiry."}
            ],
        },
        "runtime_service": {
            "kind": "runtime_service",
            "updated_at": PILOT_UPDATED_AT,
            "services": [
                {
                    "id": "backend",
                    "label": "Backend",
                    "runtime_state": "running",
                    "health_status": "success",
                    "facts": [{"id": "pid", "label": "PID", "value": 1234}],
                    "actions": [{"id": "restart_backend", "label": "Restart backend", "enabled": True, "tone": "warning"}],
                }
            ],
        },
        "action_panel": {
            "kind": "action_panel",
            "updated_at": PILOT_UPDATED_AT,
            "groups": [
                {
                    "id": "runtime",
                    "label": "Runtime",
                    "actions": [{"id": "clear_cache", "label": "Clear cache", "enabled": True, "tone": "warning"}],
                }
            ],
        },
        "provider_status": {
            "kind": "provider_status",
            "updated_at": PILOT_UPDATED_AT,
            "providers": [
                {
                    "id": "stt",
                    "label": "STT",
                    "provider": "faster_whisper",
                    "state": "ready",
                    "tone": "success",
                    "facts": [{"id": "model", "label": "Model", "value": "small.en"}],
                }
            ],
        },
        "facts_card": {
            "kind": "facts_card",
            "updated_at": PILOT_UPDATED_AT,
            "title": "Provider Facts",
            "facts": [{"id": "models", "label": "Models", "value": 3}],
        },
    }
