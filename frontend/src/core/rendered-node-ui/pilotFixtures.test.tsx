import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { nodeUiActionPath, nodeUiSurfaceDataPath } from "./api";
import { pilotNodeUiCardResponses, pilotNodeUiManifest } from "./pilotFixtures";
import { getNodeUiCardRenderer, NodeUiCard, UnsupportedNodeUiCard } from "./renderers";

describe("pilot rendered node UI fixtures", () => {
  it("covers every pilot surface with a card response and registered renderer", () => {
    const surfaces = pilotNodeUiManifest.pages.flatMap((page) => page.surfaces);

    expect(surfaces).toHaveLength(7);
    for (const surface of surfaces) {
      const response = pilotNodeUiCardResponses[surface.kind];
      expect(response?.kind).toBe(surface.kind);
      expect(getNodeUiCardRenderer(surface.kind)).not.toBe(UnsupportedNodeUiCard);
      expect(nodeUiSurfaceDataPath(pilotNodeUiManifest.node_id, surface.data_endpoint)).toMatch(
        /^\/api\/nodes\/pilot-node-1\//,
      );
    }
  });

  it("renders every pilot card kind", () => {
    const html = pilotNodeUiManifest.pages
      .flatMap((page) => page.surfaces)
      .map((surface) =>
        renderToStaticMarkup(<NodeUiCard surface={surface} data={pilotNodeUiCardResponses[surface.kind]} />),
      )
      .join("\n");

    expect(html).toContain("Node Overview");
    expect(html).toContain("Backend");
    expect(html).toContain("Provider Facts");
    expect(html).not.toContain("Unsupported card kind");
  });

  it("maps pilot action endpoints through Core", () => {
    const actions = pilotNodeUiManifest.pages.flatMap((page) =>
      page.surfaces.flatMap((surface) => surface.actions || []),
    );

    expect(actions.map((action) => nodeUiActionPath(pilotNodeUiManifest.node_id, action.endpoint))).toEqual([
      "/api/nodes/pilot-node-1/node/ui/runtime/services/backend/restart",
      "/api/nodes/pilot-node-1/node/ui/runtime/cache",
    ]);
  });
});
