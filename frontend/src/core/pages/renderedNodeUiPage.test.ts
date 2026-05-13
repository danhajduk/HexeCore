import { describe, expect, it } from "vitest";

import {
  nodeUiActionConfirmationMessage,
  nodeUiHealthFallbackEndpoint,
  nodeUiPageSearchParams,
  nodeUiRefreshPollInterval,
  nodeUiSurfacePollInterval,
  resolveNodeUiPageQueryId,
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
  health: {
    id: "node.health",
    kind: "health_strip",
    title: "Health",
    data_endpoint: "/api/node/ui/health",
    refresh: { mode: "near_live", interval_ms: 15000 },
  },
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
    data_endpoint: "/api/node/ui/health",
    refresh: { mode, interval_ms },
  };
}

describe("RenderedNodeUiPage helpers", () => {
  it("resolves the selected page or falls back to the first manifest page", () => {
    expect(resolveSelectedNodeUiPage(manifest, "runtime").id).toBe("runtime");
    expect(resolveSelectedNodeUiPage(manifest, "missing").id).toBe("overview");
    expect(resolveSelectedNodeUiPage(manifest).id).toBe("overview");
  });

  it("uses the id query parameter as the selected page key", () => {
    expect(resolveNodeUiPageQueryId("runtime")).toBe("runtime");
    expect(resolveNodeUiPageQueryId("  ")).toBeNull();
    expect(nodeUiPageSearchParams("runtime").toString()).toBe("id=runtime");
  });

  it("polls only live and near-live surfaces with explicit intervals", () => {
    expect(nodeUiSurfacePollInterval(surface("live", 2000))).toBe(2000);
    expect(nodeUiSurfacePollInterval(surface("near_live", 15000))).toBe(15000);
    expect(nodeUiSurfacePollInterval(surface("manual"))).toBeNull();
    expect(nodeUiSurfacePollInterval(surface("live"))).toBeNull();
    expect(nodeUiRefreshPollInterval({ mode: "near_live", interval_ms: 15000 })).toBe(15000);
  });

  it("keeps the rollout fallback from global health to the legacy overview health endpoint", () => {
    expect(nodeUiHealthFallbackEndpoint(surface("near_live", 15000))).toBe("/api/node/ui/overview/health");
    expect(
      nodeUiHealthFallbackEndpoint({
        ...surface("near_live", 15000),
        data_endpoint: "/api/node/ui/overview/health",
      }),
    ).toBeNull();
  });

  it("keeps only redesigned surfaces without mutating the manifest page", () => {
    const overview = {
      id: "overview",
      title: "Overview",
      surfaces: [
        { ...surface("manual"), id: "node.overview", kind: "node_overview", title: "Overview" },
        { ...surface("near_live", 15000), id: "node.health", kind: "health_strip", title: "Node Health" },
        { ...surface("manual"), id: "node.warnings", kind: "warning_banner", title: "Operational Warnings" },
        { ...surface("near_live", 15000), id: "runtime.services", kind: "runtime_service", title: "Runtime Services" },
        { ...surface("near_live", 30000), id: "runtime.providers", kind: "provider_status", title: "Provider Status" },
        { ...surface("near_live", 10000), id: "voice.endpoints", kind: "record_list", title: "Voice Endpoints" },
        { ...surface("near_live", 10000), id: "voice.endpoint_actions", kind: "action_panel", title: "Endpoint Actions" },
        { ...surface("static"), id: "node.facts", kind: "facts_card", title: "Facts" },
      ],
    };

    expect(resolveNodeUiPageSurfaces(overview).map((item) => item.id)).toEqual([
      "node.warnings",
      "runtime.services",
      "runtime.providers",
      "voice.endpoints",
      "voice.endpoint_actions",
    ]);
    expect(overview.surfaces.map((item) => item.id)).toEqual([
      "node.overview",
      "node.health",
      "node.warnings",
      "runtime.services",
      "runtime.providers",
      "voice.endpoints",
      "voice.endpoint_actions",
      "node.facts",
    ]);
  });

  it("advertises the top-level manifest health strip across every page", () => {
    const sharedHealth = surface("near_live", 15000);
    expect(
      resolveNodeUiAdvertisedHealthSurface({
        ...manifest,
        health: sharedHealth,
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

  it("keeps only redesigned cards for page snapshots", () => {
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
      {
        id: "node.warnings",
        kind: "warning_banner",
        data: { kind: "warning_banner", updated_at: "2026-05-13T01:00:00Z" },
      },
      {
        id: "runtime.services",
        kind: "runtime_service",
        data: { kind: "runtime_service", updated_at: "2026-05-13T01:00:00Z" },
      },
      {
        id: "runtime.providers",
        kind: "provider_status",
        data: { kind: "provider_status", updated_at: "2026-05-13T01:00:00Z" },
      },
      {
        id: "voice.endpoints",
        kind: "record_list",
        data: { kind: "record_list", updated_at: "2026-05-13T01:00:00Z" },
      },
      {
        id: "voice.endpoint_actions",
        kind: "action_panel",
        data: { kind: "action_panel", updated_at: "2026-05-13T01:00:00Z" },
      },
    ];

    expect(resolveNodeUiPageCards(cards).map((item) => item.id)).toEqual([
      "node.warnings",
      "runtime.services",
      "runtime.providers",
      "voice.endpoints",
      "voice.endpoint_actions",
    ]);
    expect(cards.map((item) => item.id)).toEqual([
      "node.overview",
      "node.facts",
      "node.health",
      "node.warnings",
      "runtime.services",
      "runtime.providers",
      "voice.endpoints",
      "voice.endpoint_actions",
    ]);
  });

  it("summarizes page payloads and legacy surfaces in the manifest header", () => {
    expect(
      resolveNodeUiManifestDataLabel({
        ...manifest,
        health: undefined,
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
