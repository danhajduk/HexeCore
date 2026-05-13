import { describe, expect, it } from "vitest";

import {
  nodeUiActionConfirmationMessage,
  nodeUiRefreshPollInterval,
  nodeUiSurfacePollInterval,
  resolveNodeUiAdvertisedHealthSurface,
  resolveNodeUiManifestDataLabel,
  resolveNodeUiPageCards,
  resolveNodeUiPageSurfaces,
  resolveNodeUiAction,
  resolveSelectedNodeUiPage,
} from "./RenderedNodeUiPage";
import type { NodeUiManifest, NodeUiPageCard, NodeUiSurface } from "../rendered-node-ui";

const manifest: NodeUiManifest = {
  schema_version: "1.0",
  node_id: "node-1",
  node_type: "voice",
  display_name: "Voice Node",
  pages: [
    { id: "overview", title: "Overview", surfaces: [] },
    { id: "runtime", title: "Runtime", surfaces: [] },
  ],
};

function surface(mode: NodeUiSurface["refresh"]["mode"], interval_ms?: number): NodeUiSurface {
  return {
    id: "node.health",
    kind: "health_strip",
    title: "Health",
    data_endpoint: "/api/node/ui/overview/health",
    refresh: { mode, interval_ms },
  };
}

describe("RenderedNodeUiPage helpers", () => {
  it("resolves the selected page or falls back to the first manifest page", () => {
    expect(resolveSelectedNodeUiPage(manifest, "runtime").id).toBe("runtime");
    expect(resolveSelectedNodeUiPage(manifest, "missing").id).toBe("overview");
    expect(resolveSelectedNodeUiPage(manifest).id).toBe("overview");
  });

  it("polls only live and near-live surfaces with explicit intervals", () => {
    expect(nodeUiSurfacePollInterval(surface("live", 2000))).toBe(2000);
    expect(nodeUiSurfacePollInterval(surface("near_live", 15000))).toBe(15000);
    expect(nodeUiSurfacePollInterval(surface("manual"))).toBeNull();
    expect(nodeUiSurfacePollInterval(surface("live"))).toBeNull();
    expect(nodeUiRefreshPollInterval({ mode: "near_live", interval_ms: 15000 })).toBe(15000);
  });

  it("keeps only health strip surfaces during the focused redesign pass without mutating the manifest page", () => {
    const overview = {
      id: "overview",
      title: "Overview",
      surfaces: [
        { ...surface("manual"), id: "node.overview", kind: "node_overview", title: "Overview" },
        { ...surface("near_live", 15000), id: "node.health", kind: "health_strip", title: "Node Health" },
        { ...surface("static"), id: "node.facts", kind: "facts_card", title: "Facts" },
      ],
    };

    expect(resolveNodeUiPageSurfaces(overview).map((item) => item.id)).toEqual(["node.health"]);
    expect(overview.surfaces.map((item) => item.id)).toEqual(["node.overview", "node.health", "node.facts"]);
  });

  it("advertises the first manifest health strip across every page", () => {
    const sharedHealth = surface("near_live", 15000);
    expect(
      resolveNodeUiAdvertisedHealthSurface({
        ...manifest,
        pages: [
          { id: "overview", title: "Overview", surfaces: [sharedHealth] },
          {
            id: "runtime",
            title: "Runtime",
            surfaces: [{ ...surface("manual"), id: "runtime.facts", kind: "facts_card", title: "Facts" }],
          },
        ],
      }),
    ).toBe(sharedHealth);
  });

  it("keeps only health strip cards for page snapshots during the focused redesign pass", () => {
    const cards: NodeUiPageCard[] = [
      {
        id: "node.overview",
        kind: "node_overview",
        data: { kind: "node_overview", updated_at: "2026-05-13T01:00:00Z" },
      },
      {
        id: "node.facts",
        kind: "facts_card",
        data: { kind: "facts_card", updated_at: "2026-05-13T01:00:00Z" },
      },
      {
        id: "node.health",
        kind: "health_strip",
        data: { kind: "health_strip", updated_at: "2026-05-13T01:00:00Z" },
      },
    ];

    expect(resolveNodeUiPageCards(cards).map((item) => item.id)).toEqual(["node.health"]);
    expect(cards.map((item) => item.id)).toEqual(["node.overview", "node.facts", "node.health"]);
  });

  it("summarizes page payloads and legacy surfaces in the manifest header", () => {
    expect(
      resolveNodeUiManifestDataLabel({
        ...manifest,
        pages: [
          {
            id: "overview",
            title: "Overview",
            page_endpoint: "/api/node/ui/pages/overview",
            refresh: { mode: "near_live", interval_ms: 15000 },
            surfaces: [],
          },
          {
            id: "runtime",
            title: "Runtime",
            surfaces: [surface("manual")],
          },
        ],
      }),
    ).toBe("1 page payload · 1 surface");
  });

  it("resolves executable action metadata from surface manifests", () => {
    const actionSurface: NodeUiSurface = {
      ...surface("manual"),
      actions: [
        {
          id: "restart",
          label: "Restart",
          method: "POST",
          endpoint: "/api/node/ui/runtime/restart",
          confirmation: { required: true, message: "Restart service?" },
        },
      ],
    };

    const action = resolveNodeUiAction(actionSurface, { id: "restart", enabled: true });

    expect(action?.endpoint).toBe("/api/node/ui/runtime/restart");
    expect(resolveNodeUiAction(actionSurface, { id: "missing", enabled: true })).toBeNull();
    expect(action ? nodeUiActionConfirmationMessage(action) : null).toBe("Restart service?");
  });
});
