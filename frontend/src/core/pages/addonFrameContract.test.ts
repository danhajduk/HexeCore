import { describe, expect, it } from "vitest";
import { addonUiFallbackReason, resolveAddonUiEmbedState } from "./addonFrameContract";

describe("addonFrameContract", () => {
  it("prefers backend-provided ui_embed_target", () => {
    const resolved = resolveAddonUiEmbedState("mqtt", {
      loaded: true,
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

  it("uses direct published host port while addon is not loaded", () => {
    const resolved = resolveAddonUiEmbedState("mqtt", {
      loaded: false,
      runtime_state: "running",
      ui_reachable: true,
      ui_reason: "ready",
      ui_embed_target: "/ui/addons/mqtt",
      standalone_runtime: {
        published_ports: ["0.0.0.0:18080->8080/tcp"],
      },
    });
    expect(resolved.frameSrc.endsWith(":18080")).toBe(true);
    expect(resolved.frameSrc.includes("/ui/addons/mqtt")).toBe(false);
  });

  it("maps fallback reasons to readable text", () => {
    expect(addonUiFallbackReason("no_published_ports")).toContain("published UI ports");
  });
});
