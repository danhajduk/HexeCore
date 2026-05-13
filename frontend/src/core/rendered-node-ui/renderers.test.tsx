import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  HealthStripCard,
  NODE_UI_CARD_RENDERERS,
  NodeUiCard,
  UnsupportedNodeUiCard,
  getNodeUiCardRenderer,
} from "./renderers";
import type {
  ActionPanelCardResponse,
  HealthStripCardResponse,
  NodeUiSurface,
  ProviderStatusCardResponse,
  RecordListCardResponse,
  RuntimeServiceCardResponse,
  WarningBannerCardResponse,
} from "./types";

const surface: NodeUiSurface = {
  id: "node.health",
  kind: "health_strip",
  title: "Node Health",
  data_endpoint: "/api/node/ui/health",
  refresh: { mode: "near_live", interval_ms: 15000 },
};

describe("rendered node UI renderers", () => {
  it("registers the initial shared card kinds", () => {
    expect(Object.keys(NODE_UI_CARD_RENDERERS).sort()).toEqual([
      "action_panel",
      "facts_card",
      "health_strip",
      "node_overview",
      "provider_status",
      "record_list",
      "runtime_service",
      "warning_banner",
    ]);
    expect(getNodeUiCardRenderer("health_strip")).toBe(HealthStripCard);
    expect(getNodeUiCardRenderer("unknown_kind")).toBe(UnsupportedNodeUiCard);
  });

  it("renders health strip data", () => {
    const data: HealthStripCardResponse = {
      kind: "health_strip",
      updated_at: "2026-05-13T01:00:00Z",
      items: [
        { state_name: "Trust", current_state: "trusted", tone: "success" },
        { state_name: "Runtime", current_state: "running", tone: "success" },
      ],
    };

    const html = renderToStaticMarkup(<NodeUiCard surface={surface} data={data} />);

    expect(html).not.toContain("Node Health");
    expect(html).toContain("Trust");
    expect(html).toContain("trusted");
    expect(html).toContain("Runtime");
  });

  it("renders unsupported card states safely", () => {
    const html = renderToStaticMarkup(
      <NodeUiCard
        surface={{ ...surface, kind: "future_card", title: "Future Card" }}
        data={{ kind: "future_card", updated_at: "2026-05-13T01:00:00Z" } as any}
      />,
    );

    expect(html).toContain("Future Card");
    expect(html).toContain("Unsupported card kind: future_card");
  });

  it("marks empty card states for neutral styling", () => {
    const data: WarningBannerCardResponse = {
      kind: "warning_banner",
      updated_at: "2026-05-13T01:00:00Z",
      empty: true,
      warnings: [],
    };

    const html = renderToStaticMarkup(
      <NodeUiCard surface={{ ...surface, kind: "warning_banner", title: "Operational Warnings" }} data={data} />,
    );

    expect(html).toContain("kind-warning_banner");
    expect(html).toContain("is-empty");
    expect(html).toContain("No data.");
  });

  it("renders runtime service payloads from the voice node", () => {
    const data: RuntimeServiceCardResponse = {
      kind: "runtime_service",
      updated_at: "2026-05-13T01:00:00Z",
      services: [
        {
          id: "backend",
          label: "Backend",
          state: "running",
          tone: "success",
          resource_usage: {
            process_cpu_percent: 7.25,
            process_memory_rss_bytes: 91238400,
            system_load_1m: 1.5,
          },
        },
      ],
    };

    const html = renderToStaticMarkup(
      <NodeUiCard surface={{ ...surface, kind: "runtime_service", title: "Runtime Services" }} data={data} />,
    );

    expect(html).toContain("Backend");
    expect(html).toContain("Running");
    expect(html).toContain("7.25%");
    expect(html).toContain("87.0 MB");
  });

  it("renders provider status payloads from the voice node", () => {
    const data: ProviderStatusCardResponse = {
      kind: "provider_status",
      updated_at: "2026-05-13T01:00:00Z",
      providers: [
        {
          id: "tts",
          label: "TTS Provider",
          provider: "piper",
          state: "ready",
          tone: "success",
          facts: [{ id: "model", label: "Model", value: "en_US-lessac" }],
        },
      ],
    };

    const html = renderToStaticMarkup(
      <NodeUiCard surface={{ ...surface, kind: "provider_status", title: "Provider Status" }} data={data} />,
    );

    expect(html).toContain("TTS Provider");
    expect(html).toContain("piper");
    expect(html).toContain("en_US-lessac");
  });

  it("renders endpoint record list payloads from the voice node", () => {
    const data: RecordListCardResponse = {
      kind: "record_list",
      updated_at: "2026-05-13T01:00:00Z",
      summary: { endpoint_count: 2, active_endpoint_id: "esp-box-1" },
      columns: [
        { id: "name", label: "Name" },
        { id: "status", label: "Status" },
        { id: "device_state", label: "Device" },
        { id: "firmware_version", label: "Firmware" },
      ],
      records: [
        {
          id: "esp-box-1",
          endpoint_id: "esp-box-1",
          name: "Kitchen",
          status: "online",
          tone: "success",
          active: true,
          device_state: "idle",
          firmware_version: "0.1.0",
        },
      ],
    };

    const html = renderToStaticMarkup(
      <NodeUiCard surface={{ ...surface, kind: "record_list", title: "Voice Endpoints" }} data={data} />,
    );

    expect(html).toContain("Kitchen");
    expect(html).toContain("Online");
    expect(html).toContain("Active");
    expect(html).toContain("0.1.0");
    expect(html).toContain("Endpoint Count");
  });

  it("keeps action buttons disabled until an action handler is provided", () => {
    const data: ActionPanelCardResponse = {
      kind: "action_panel",
      updated_at: "2026-05-13T01:00:00Z",
      groups: [{ id: "runtime", label: "Runtime", actions: [{ id: "restart", label: "Restart", enabled: true }] }],
    };

    const disabledHtml = renderToStaticMarkup(<NodeUiCard surface={{ ...surface, kind: "action_panel" }} data={data} />);
    const enabledHtml = renderToStaticMarkup(
      <NodeUiCard surface={{ ...surface, kind: "action_panel" }} data={data} onAction={vi.fn()} />,
    );

    expect(disabledHtml).toContain("disabled");
    expect(enabledHtml).not.toContain("disabled");
  });
});
