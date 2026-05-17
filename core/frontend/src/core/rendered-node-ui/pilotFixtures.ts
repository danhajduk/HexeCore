import type { NodeUiCardResponse, NodeUiManifest } from "./types";

export const pilotNodeUiManifest: NodeUiManifest = {
  schema_version: "1.0",
  manifest_revision: "pilot-rev-1",
  node_id: "pilot-node-1",
  node_type: "voice",
  display_name: "Pilot Voice Node",
  health: {
    id: "node.health",
    kind: "health_strip",
    title: "Health",
    data_endpoint: "/api/node/ui/health",
    refresh: { mode: "near_live", interval_ms: 15000 },
  },
  pages: [
    {
      id: "overview",
      title: "Overview",
      surfaces: [
        {
          id: "node.warnings",
          kind: "warning_banner",
          title: "Operational Warnings",
          data_endpoint: "/api/node/ui/overview/warnings",
          actions: [
            {
              id: "refresh_governance",
              label: "Refresh governance",
              method: "POST",
              endpoint: "/api/node/ui/actions/refresh-status",
            },
            {
              id: "open_provider_setup",
              label: "Open provider setup",
              method: "POST",
              endpoint: "/api/node/ui/actions/open-provider-setup",
            },
          ],
          refresh: { mode: "manual" },
        },
      ],
    },
  ],
};

export const pilotNodeUiCardResponses: Record<string, NodeUiCardResponse> = {
  health_strip: {
    kind: "health_strip",
    updated_at: "2026-05-13T01:00:00Z",
    items: [
      { state_name: "Lifecycle", current_state: "Operational", tone: "success" },
      { state_name: "Trust", current_state: "Trusted", tone: "success" },
      { state_name: "Core API", current_state: "Connected", tone: "success" },
      { state_name: "Governance", current_state: "Fresh", tone: "info" },
      { state_name: "Providers", current_state: "Configured", tone: "info" },
      { state_name: "STT", current_state: "External_faster_whisper", tone: "success" },
      { state_name: "TTS", current_state: "Piper", tone: "success" },
    ],
  },
  warning_banner: {
    kind: "warning_banner",
    updated_at: "2026-05-13T01:00:00Z",
    warnings: [
      {
        id: "governance",
        title: "Governance refresh due",
        message: "Policy sync is older than the preferred freshness window.",
        tone: "warning",
        actions: [{ id: "refresh_governance", label: "Refresh governance", enabled: true, tone: "warning" }],
      },
      {
        id: "provider.stt",
        title: "STT engine using fallback",
        message: "The node is ready, but speech recognition is using the deterministic fallback engine.",
        tone: "info",
        actions: [{ id: "open_provider_setup", label: "Open provider setup", enabled: true, tone: "info" }],
      },
    ],
  },
};
