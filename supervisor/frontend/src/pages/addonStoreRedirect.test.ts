import { describe, expect, it } from "vitest";
import { resolveUiRedirectTarget, standaloneUiFallbackMessage } from "./addonStoreRedirect";

describe("addonStoreRedirect", () => {
  it("prefers explicit ui_redirect_target", () => {
    expect(resolveUiRedirectTarget({ ui_reachable: true, ui_redirect_target: "/addons/mqtt" }, "mqtt")).toBe(
      "/addons/mqtt",
    );
  });

  it("builds default target when ui is reachable", () => {
    expect(resolveUiRedirectTarget({ ui_reachable: true }, "mqtt")).toBe("/addons/mqtt");
  });

  it("returns null when not reachable", () => {
    expect(resolveUiRedirectTarget({ ui_reachable: false }, "mqtt")).toBeNull();
    expect(resolveUiRedirectTarget(undefined, "mqtt")).toBeNull();
  });

  it("returns fallback message with addon id", () => {
    expect(standaloneUiFallbackMessage("mqtt")).toContain("mqtt");
  });
});
