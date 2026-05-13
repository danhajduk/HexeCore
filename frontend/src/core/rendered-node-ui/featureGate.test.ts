import { describe, expect, it } from "vitest";

import { RENDERED_NODE_UI_STORAGE_KEY, parseRenderedNodeUiFlag, renderedNodeUiFeatureEnabled } from "./featureGate";

describe("rendered node UI feature gate", () => {
  it("parses explicit enabled and disabled flag values", () => {
    expect(parseRenderedNodeUiFlag("1")).toBe(true);
    expect(parseRenderedNodeUiFlag("enabled")).toBe(true);
    expect(parseRenderedNodeUiFlag("0")).toBe(false);
    expect(parseRenderedNodeUiFlag("disabled")).toBe(false);
    expect(parseRenderedNodeUiFlag("maybe")).toBeNull();
  });

  it("prefers local storage override over environment value", () => {
    const storage = {
      getItem: (key: string) => (key === RENDERED_NODE_UI_STORAGE_KEY ? "false" : null),
    };

    expect(renderedNodeUiFeatureEnabled("true", storage)).toBe(false);
  });

  it("defaults to disabled", () => {
    expect(renderedNodeUiFeatureEnabled("", null)).toBe(false);
  });
});
