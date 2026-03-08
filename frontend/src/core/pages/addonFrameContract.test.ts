import { describe, expect, it } from "vitest";
import { addonUiFallbackReason, resolveAddonUiEmbedState } from "./addonFrameContract";

describe("addonFrameContract", () => {
  it("prefers backend-provided ui_embed_target", () => {
    const resolved = resolveAddonUiEmbedState("mqtt", {
      ui_reachable: true,
      ui_embed_target: "/ui/addons/mqtt",
      ui_reason: "ready",
    });
    expect(resolved.reachable).toBe(true);
    expect(resolved.reason).toBe("ready");
    expect(resolved.frameSrc.endsWith("/ui/addons/mqtt")).toBe(true);
  });

  it("falls back to default frame URL when target is missing", () => {
    const resolved = resolveAddonUiEmbedState("mqtt", { ui_reachable: false, ui_reason: "no_published_ports" });
    expect(resolved.frameSrc.endsWith("/ui/addons/mqtt")).toBe(true);
    expect(resolved.reachable).toBe(false);
  });

  it("maps fallback reasons to readable text", () => {
    expect(addonUiFallbackReason("no_published_ports")).toContain("published UI ports");
  });
});
