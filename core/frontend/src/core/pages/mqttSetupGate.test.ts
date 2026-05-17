import { describe, expect, it } from "vitest";
import { resolveMqttSetupSection } from "./mqttSetupGate";

describe("resolveMqttSetupSection", () => {
  it("forces setup section when setup is required and incomplete", () => {
    const res = resolveMqttSetupSection("runtime", {
      setup: { requires_setup: true, setup_complete: false },
    });
    expect(res.gateActive).toBe(true);
    expect(res.redirected).toBe(true);
    expect(res.section).toBe("setup");
  });

  it("allows protected sections after setup completes", () => {
    const res = resolveMqttSetupSection("runtime", {
      setup: { requires_setup: true, setup_complete: true },
    });
    expect(res.gateActive).toBe(false);
    expect(res.redirected).toBe(false);
    expect(res.section).toBe("runtime");
  });

  it("defaults empty section to overview when gate is not active", () => {
    const res = resolveMqttSetupSection("", {
      setup: { requires_setup: false, setup_complete: false },
    });
    expect(res.gateActive).toBe(false);
    expect(res.redirected).toBe(false);
    expect(res.section).toBe("overview");
  });

  it("allows setup section while gate is active", () => {
    const res = resolveMqttSetupSection("setup", {
      setup: { requires_setup: true, setup_complete: false },
    });
    expect(res.gateActive).toBe(true);
    expect(res.redirected).toBe(false);
    expect(res.section).toBe("setup");
  });

  it("keeps protected sections gated when setup remains incomplete after failure", () => {
    const res = resolveMqttSetupSection("overview", {
      setup: { requires_setup: true, setup_complete: false },
    });
    expect(res.gateActive).toBe(true);
    expect(res.redirected).toBe(true);
    expect(res.section).toBe("setup");
  });
});
