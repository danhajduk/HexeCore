import { describe, expect, it } from "vitest";

import {
  executeNodeUiAction,
  fetchNodeSurfaceData,
  fetchNodeUiManifest,
  nodeUiActionPath,
  nodeUiManifestPath,
  nodeUiSurfaceDataPath,
  type NodeUiFetcher,
} from "./api";

describe("rendered node UI data API", () => {
  it("builds the Core manifest fetch path", () => {
    expect(nodeUiManifestPath("node 1")).toBe("/api/nodes/node%201/ui-manifest");
  });

  it("maps node-local API data endpoints through the Core node proxy", () => {
    expect(nodeUiSurfaceDataPath("node-1", "/api/node/ui/overview/health")).toBe(
      "/api/nodes/node-1/node/ui/overview/health",
    );
  });

  it("rejects unsafe or non-Core-routable data endpoints", () => {
    expect(() => nodeUiSurfaceDataPath("node-1", "http://node.local/api/node/ui/health")).toThrow(
      "node_ui_endpoint_must_be_relative",
    );
    expect(() => nodeUiSurfaceDataPath("node-1", "//node.local/api/node/ui/health")).toThrow(
      "node_ui_endpoint_must_be_relative",
    );
    expect(() => nodeUiSurfaceDataPath("node-1", "/status")).toThrow("node_ui_endpoint_must_start_with_api");
  });

  it("loads manifest fetch responses with admin session credentials", async () => {
    const calls: Array<{ input: string; init?: RequestInit }> = [];
    const fetcher: NodeUiFetcher = async (input, init) => {
      calls.push({ input: String(input), init });
      return new Response(
        JSON.stringify({
          node_id: "node-1",
          ok: true,
          status: "available",
          manifest_revision: "rev-1",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    };

    const response = await fetchNodeUiManifest("node-1", { fetcher });

    expect(response.ok).toBe(true);
    expect(response.manifest_revision).toBe("rev-1");
    expect(calls).toHaveLength(1);
    expect(calls[0].input).toBe("/api/nodes/node-1/ui-manifest");
    expect(calls[0].init?.credentials).toBe("include");
    expect(calls[0].init?.cache).toBe("no-store");
  });

  it("loads surface data through Core", async () => {
    const fetcher: NodeUiFetcher = async (input) =>
      new Response(JSON.stringify({ state: "healthy", path: String(input) }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });

    const response = await fetchNodeSurfaceData<{ state: string; path: string }>(
      "node-1",
      "/api/node/ui/overview/health",
      { fetcher },
    );

    expect(response.state).toBe("healthy");
    expect(response.path).toBe("/api/nodes/node-1/node/ui/overview/health");
  });

  it("executes node actions through Core", async () => {
    const calls: Array<{ input: string; init?: RequestInit }> = [];
    const fetcher: NodeUiFetcher = async (input, init) => {
      calls.push({ input: String(input), init });
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    };

    const response = await executeNodeUiAction(
      "node-1",
      { method: "POST", endpoint: "/api/node/ui/runtime/restart" },
      { service_id: "backend" },
      { fetcher },
    );

    expect(nodeUiActionPath("node-1", "/api/node/ui/runtime/restart")).toBe(
      "/api/nodes/node-1/node/ui/runtime/restart",
    );
    expect(response.ok).toBe(true);
    expect(calls[0].input).toBe("/api/nodes/node-1/node/ui/runtime/restart");
    expect(calls[0].init?.method).toBe("POST");
    expect(calls[0].init?.credentials).toBe("include");
    expect(calls[0].init?.body).toBe(JSON.stringify({ service_id: "backend" }));
  });

  it("handles empty action responses", async () => {
    const fetcher: NodeUiFetcher = async () => new Response(null, { status: 204 });

    await expect(
      executeNodeUiAction("node-1", { method: "DELETE", endpoint: "/api/node/ui/runtime/cache" }, undefined, {
        fetcher,
      }),
    ).resolves.toEqual({});
  });

  it("surfaces structured error details", async () => {
    const fetcher: NodeUiFetcher = async () =>
      new Response(JSON.stringify({ detail: "invalid_manifest" }), {
        status: 502,
        headers: { "content-type": "application/json" },
      });

    await expect(fetchNodeUiManifest("node-1", { fetcher })).rejects.toThrow("invalid_manifest");
  });
});
