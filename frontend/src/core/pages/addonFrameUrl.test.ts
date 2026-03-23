import { describe, expect, it } from "vitest";
import { addonUiFrameSrc } from "./addonFrameUrl";

describe("addonUiFrameSrc", () => {
  it("uses provided backend base override", () => {
    expect(addonUiFrameSrc("mqtt", "http://10.0.0.100:9001/")).toBe("http://10.0.0.100:9001/addons/proxy/mqtt/");
  });

  it("encodes addon id", () => {
    expect(addonUiFrameSrc("hello world", "http://127.0.0.1:9001")).toBe("http://127.0.0.1:9001/addons/proxy/hello%20world/");
  });

  it("returns empty string for empty addon id", () => {
    expect(addonUiFrameSrc("   ", "http://127.0.0.1:9001")).toBe("");
  });

  it("defaults to the backend proxy origin when no override is provided", () => {
    expect(addonUiFrameSrc("mqtt")).toContain("/addons/proxy/mqtt/");
  });

  it("uses the same origin for managed public tunnel hostnames", () => {
    expect(
      addonUiFrameSrc("mqtt", "", {
        origin: "https://a75d480287c33cab.hexe-ai.com",
        hostname: "a75d480287c33cab.hexe-ai.com",
        protocol: "https:",
        port: "",
      }),
    ).toBe("https://a75d480287c33cab.hexe-ai.com/addons/proxy/mqtt/");
  });

  it("keeps the backend port fallback for LAN/default-port access", () => {
    expect(
      addonUiFrameSrc("mqtt", "", {
        origin: "http://10.0.0.100",
        hostname: "10.0.0.100",
        protocol: "http:",
        port: "",
      }),
    ).toBe("http://10.0.0.100:9001/addons/proxy/mqtt/");
  });

  it("keeps the backend port fallback for frontend dev servers", () => {
    expect(
      addonUiFrameSrc("mqtt", "", {
        origin: "http://127.0.0.1:5173",
        hostname: "127.0.0.1",
        protocol: "http:",
        port: "5173",
      }),
    ).toBe("http://127.0.0.1:9001/addons/proxy/mqtt/");
  });
});
