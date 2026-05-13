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
          id: "node.health",
          kind: "health_strip",
          title: "Health",
          data_endpoint: "/api/node/ui/overview/health",
          refresh: { mode: "near_live", interval_ms: 15000 },
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
      { id: "lifecycle", label: "Lifecycle", value: "Operational", tone: "success" },
      { id: "trust", label: "Trust", value: "Trusted", tone: "success" },
      { id: "core_api", label: "Core API", value: "Connected", tone: "success" },
      { id: "governance", label: "Governance", value: "Fresh", tone: "info" },
      { id: "providers", label: "Providers", value: "Configured", tone: "info" },
      { id: "stt", label: "STT", value: "External_faster_whisper", tone: "success" },
      { id: "tts", label: "TTS", value: "Piper", tone: "success" },
    ],
  },
};
