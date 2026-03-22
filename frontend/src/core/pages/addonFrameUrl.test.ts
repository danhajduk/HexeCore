import { describe, expect, it } from "vitest";
import { addonUiFrameSrc } from "./addonFrameUrl";

describe("addonUiFrameSrc", () => {
  it("defaults to the same-origin addon proxy path", () => {
    expect(addonUiFrameSrc("mqtt")).toBe("/ui/addons/mqtt");
  });

  it("uses provided backend base override", () => {
    expect(addonUiFrameSrc("mqtt", "http://10.0.0.100:9001/")).toBe("http://10.0.0.100:9001/ui/addons/mqtt");
  });

  it("encodes addon id", () => {
    expect(addonUiFrameSrc("hello world")).toBe("/ui/addons/hello%20world");
  });

  it("returns empty string for empty addon id", () => {
    expect(addonUiFrameSrc("   ", "http://127.0.0.1:9001")).toBe("");
  });
});
