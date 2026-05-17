import { describe, expect, it } from "vitest";

import { nodeCanOpenRenderedCoreUi, renderedCoreUiAdvertised, renderedCoreUiUnavailableReason } from "./NodeDetails";

describe("node details rendered Core UI entrypoint", () => {
  it("checks the Core UI manifest for trusted nodes", () => {
    expect(nodeCanOpenRenderedCoreUi({ status: { trust_status: "trusted" } as any })).toBe(true);
  });

  it("hides the Core UI entrypoint for untrusted nodes", () => {
    expect(nodeCanOpenRenderedCoreUi({ status: { trust_status: "approved" } as any })).toBe(false);
    expect(nodeCanOpenRenderedCoreUi(null)).toBe(false);
  });

  it("enables rendered Core UI only when the manifest is advertised", () => {
    const node = { status: { trust_status: "trusted" } as any };

    expect(renderedCoreUiAdvertised(node, { data: { ok: true } as any })).toBe(true);
    expect(renderedCoreUiAdvertised(node, { data: { ok: false } as any })).toBe(false);
    expect(renderedCoreUiAdvertised({ status: { trust_status: "approved" } as any }, { data: { ok: true } as any })).toBe(false);
  });

  it("exposes an unavailable reason while checking or when manifest fetch fails", () => {
    expect(renderedCoreUiUnavailableReason({ status: "loading", data: null, error: null })).toBe("Checking Core UI manifest.");
    expect(
      renderedCoreUiUnavailableReason({
        status: "ready",
        data: { ok: false, status: "invalid_manifest", detail: "bad manifest" } as any,
        error: null,
      }),
    ).toBe("bad manifest");
  });
});
