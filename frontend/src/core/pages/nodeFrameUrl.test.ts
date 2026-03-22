import { describe, expect, it } from "vitest";
import { nodeUiFrameSrc } from "./nodeFrameUrl";

describe("nodeUiFrameSrc", () => {
  it("returns empty string for empty hostname", () => {
    expect(nodeUiFrameSrc("node-1", "   ", "   ")).toBe("");
  });

  it("uses the Core node proxy when an endpoint exists", () => {
    expect(nodeUiFrameSrc("node-1", "https://node.example.test/ui/", "node.local")).toContain("/nodes/node-1/ui/");
  });

  it("uses the Core node proxy when only a hostname exists", () => {
    expect(nodeUiFrameSrc("node-1", "", "node.local")).toContain("/nodes/node-1/ui/");
  });

  it("returns empty string for invalid non-absolute endpoints", () => {
    expect(nodeUiFrameSrc("node-1", "/ui", "node.local")).toBe("");
  });
});
