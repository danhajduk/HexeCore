import type { NodeUiCardResponse, NodeUiManifest } from "./types";

export const pilotNodeUiManifest: NodeUiManifest = {
  schema_version: "1.0",
  manifest_revision: "pilot-rev-1",
  node_id: "pilot-node-1",
  node_type: "voice",
  display_name: "Pilot Voice Node",
  pages: [
    {
      id: "overview",
      title: "Overview",
      surfaces: [
        {
          id: "node.overview",
          kind: "node_overview",
          title: "Node Overview",
          data_endpoint: "/api/node/ui/overview",
          refresh: { mode: "manual" },
        },
        {
          id: "node.health",
          kind: "health_strip",
          title: "Health",
          data_endpoint: "/api/node/ui/overview/health",
          refresh: { mode: "near_live", interval_ms: 15000 },
        },
      ],
    },
    {
      id: "runtime",
      title: "Runtime",
      surfaces: [
        {
          id: "runtime.services",
          kind: "runtime_service",
          title: "Services",
          data_endpoint: "/api/node/ui/runtime/services",
          actions: [
            {
              id: "restart_backend",
              label: "Restart backend",
              method: "POST",
              endpoint: "/api/node/ui/runtime/services/backend/restart",
              destructive: true,
              confirmation: { required: true, message: "Restart backend service?", tone: "warning" },
            },
          ],
          refresh: { mode: "manual" },
        },
        {
          id: "runtime.actions",
          kind: "action_panel",
          title: "Runtime Actions",
          data_endpoint: "/api/node/ui/runtime/actions",
          actions: [
            {
              id: "clear_cache",
              label: "Clear cache",
              method: "DELETE",
              endpoint: "/api/node/ui/runtime/cache",
              sensitive: true,
              confirmation: { required: true, message: "Clear runtime cache?", tone: "warning" },
            },
          ],
          refresh: { mode: "manual" },
        },
      ],
    },
    {
      id: "providers",
      title: "Providers",
      surfaces: [
        {
          id: "providers.status",
          kind: "provider_status",
          title: "Providers",
          data_endpoint: "/api/node/ui/providers/status",
          refresh: { mode: "near_live", interval_ms: 30000 },
        },
        {
          id: "providers.facts",
          kind: "facts_card",
          title: "Provider Facts",
          data_endpoint: "/api/node/ui/providers/facts",
          refresh: { mode: "static" },
        },
        {
          id: "providers.warnings",
          kind: "warning_banner",
          title: "Warnings",
          data_endpoint: "/api/node/ui/providers/warnings",
          refresh: { mode: "manual" },
        },
      ],
    },
  ],
};

export const pilotNodeUiCardResponses: Record<string, NodeUiCardResponse> = {
  node_overview: {
    kind: "node_overview",
    updated_at: "2026-05-13T01:00:00Z",
    identity: [{ id: "node_id", label: "Node ID", value: "pilot-node-1" }],
    lifecycle: [{ id: "runtime", label: "Runtime", value: "running", tone: "success" }],
  },
  health_strip: {
    kind: "health_strip",
    updated_at: "2026-05-13T01:00:00Z",
    items: [{ id: "trust", label: "Trust", value: "trusted", tone: "success" }],
  },
  runtime_service: {
    kind: "runtime_service",
    updated_at: "2026-05-13T01:00:00Z",
    services: [
      {
        id: "backend",
        label: "Backend",
        runtime_state: "running",
        health_status: "success",
        actions: [{ id: "restart_backend", label: "Restart backend", enabled: true, tone: "warning" }],
      },
    ],
  },
  action_panel: {
    kind: "action_panel",
    updated_at: "2026-05-13T01:00:00Z",
    groups: [
      {
        id: "runtime",
        label: "Runtime",
        actions: [{ id: "clear_cache", label: "Clear cache", enabled: true, tone: "warning" }],
      },
    ],
  },
  provider_status: {
    kind: "provider_status",
    updated_at: "2026-05-13T01:00:00Z",
    providers: [{ id: "stt", label: "STT", provider: "faster_whisper", state: "ready", tone: "success" }],
  },
  facts_card: {
    kind: "facts_card",
    updated_at: "2026-05-13T01:00:00Z",
    facts: [{ id: "models", label: "Models", value: 3 }],
  },
  warning_banner: {
    kind: "warning_banner",
    updated_at: "2026-05-13T01:00:00Z",
    warnings: [{ id: "governance", title: "Governance refresh due", tone: "warning" }],
  },
};
