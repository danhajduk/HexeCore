import { describe, expect, it } from "vitest";

import { nodeUiErrorState, nodeUiLoadingState } from "./hooks";
import type { NodeUiLoadState } from "./types";

describe("rendered node UI load state helpers", () => {
  it("uses the loading state only before data has loaded", () => {
    expect(nodeUiLoadingState({ status: "idle", data: null, error: null })).toEqual({
      status: "loading",
      data: null,
      error: null,
    });

    const ready: NodeUiLoadState<{ page_id: string }> = {
      status: "ready",
      data: { page_id: "runtime" },
      error: null,
    };

    expect(nodeUiLoadingState(ready)).toEqual(ready);
  });

  it("preserves existing data when a background refresh fails", () => {
    const current: NodeUiLoadState<{ page_id: string }> = {
      status: "ready",
      data: { page_id: "runtime" },
      error: null,
    };

    expect(nodeUiErrorState(current, new Error("refresh_failed"))).toEqual({
      status: "ready",
      data: { page_id: "runtime" },
      error: "refresh_failed",
    });
  });
});
