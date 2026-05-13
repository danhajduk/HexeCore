import { describe, expect, it } from "vitest";

import { nodeCanOpenRenderedCoreUi } from "./NodeDetails";

describe("node details rendered Core UI entrypoint", () => {
  it("shows the Core UI entrypoint for trusted nodes", () => {
    expect(nodeCanOpenRenderedCoreUi({ status: { trust_status: "trusted" } as any })).toBe(true);
  });

  it("hides the Core UI entrypoint for untrusted nodes", () => {
    expect(nodeCanOpenRenderedCoreUi({ status: { trust_status: "approved" } as any })).toBe(false);
    expect(nodeCanOpenRenderedCoreUi(null)).toBe(false);
  });
});
