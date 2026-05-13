import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { nodeUiSurfaceDataPath } from "./api";
import { pilotNodeUiCardResponses, pilotNodeUiManifest } from "./pilotFixtures";
import { getNodeUiCardRenderer, NodeUiCard, UnsupportedNodeUiCard } from "./renderers";

describe("pilot rendered node UI fixtures", () => {
  it("covers every pilot surface with a card response and registered renderer", () => {
    const surfaces = pilotNodeUiManifest.pages
      .flatMap((page) => page.surfaces)
      .concat(pilotNodeUiManifest.health ? [pilotNodeUiManifest.health] : []);

    expect(surfaces).toHaveLength(2);
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
      .concat(pilotNodeUiManifest.health ? [pilotNodeUiManifest.health] : [])
      .map((surface) =>
        renderToStaticMarkup(<NodeUiCard surface={surface} data={pilotNodeUiCardResponses[surface.kind]} />),
      )
      .join("\n");

    expect(html).toContain("Lifecycle");
    expect(html).toContain("External_faster_whisper");
    expect(html).toContain("Governance refresh due");
    expect(html).toContain("STT engine using fallback");
    expect(html).not.toContain("Unsupported card kind");
  });
});
