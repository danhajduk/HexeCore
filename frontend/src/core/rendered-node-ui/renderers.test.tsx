import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  HealthStripCard,
  NODE_UI_CARD_RENDERERS,
  NodeUiCard,
  UnsupportedNodeUiCard,
  getNodeUiCardRenderer,
} from "./renderers";
import type { ActionPanelCardResponse, HealthStripCardResponse, NodeUiSurface } from "./types";

const surface: NodeUiSurface = {
  id: "node.health",
  kind: "health_strip",
  title: "Node Health",
  data_endpoint: "/api/node/ui/overview/health",
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
        { id: "trust", label: "Trust", value: "trusted", tone: "success" },
        { id: "runtime", label: "Runtime", value: "running", tone: "success" },
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
