import { describe, expect, it } from "vitest";
import { accessPrompt, assistantEntry } from "./accessState";

describe("accessPrompt", () => {
  it("does not expose either authentication form before device discovery completes", () => {
    expect(accessPrompt(null)).toBe("loading");
  });

  it("selects one stable prompt after device discovery", () => {
    expect(accessPrompt(false)).toBe("login");
    expect(accessPrompt(true)).toBe("passkey");
  });

  it("does not bootstrap an enrolled device from a pre-unlock access token", () => {
    expect(assistantEntry(true, true, false)).toBe("locked");
    expect(assistantEntry(true, true, true)).toBe("authenticated");
  });

  it("allows ordinary authenticated browsers without a device passkey", () => {
    expect(assistantEntry(false, true, false)).toBe("authenticated");
    expect(assistantEntry(false, false, false)).toBe("locked");
  });
});
