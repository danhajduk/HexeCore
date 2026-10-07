import { describe, expect, it } from "vitest";
import { accessPrompt } from "./accessState";

describe("accessPrompt", () => {
  it("does not expose either authentication form before device discovery completes", () => {
    expect(accessPrompt(null)).toBe("loading");
  });

  it("selects one stable prompt after device discovery", () => {
    expect(accessPrompt(false)).toBe("login");
    expect(accessPrompt(true)).toBe("passkey");
  });
});
