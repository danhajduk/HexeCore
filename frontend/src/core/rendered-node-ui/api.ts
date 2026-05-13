import { API_BASE } from "../api/client";
import type { NodeUiManifestFetchResponse } from "./types";

export type NodeUiFetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

type FetchOptions = {
  fetcher?: NodeUiFetcher;
  signal?: AbortSignal;
};

function requireNodeId(nodeId: string): string {
  const trimmed = String(nodeId || "").trim();
  if (!trimmed) throw new Error("node_id_required");
  return trimmed;
}

function readCoreEndpointPath(endpoint: string): string {
  const trimmed = String(endpoint || "").trim();
  if (!trimmed) throw new Error("node_ui_endpoint_required");
  if (trimmed.startsWith("//") || /^[a-z][a-z0-9+.-]*:/i.test(trimmed)) {
    throw new Error("node_ui_endpoint_must_be_relative");
  }
  if (!trimmed.startsWith("/api/")) {
    throw new Error("node_ui_endpoint_must_start_with_api");
  }
  return trimmed.slice("/api/".length).replace(/^\/+/, "");
}

async function readError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string" && payload.detail.trim()) return payload.detail.trim();
    if (typeof payload?.error_code === "string" && payload.error_code.trim()) return payload.error_code.trim();
    if (typeof payload?.error === "string" && payload.error.trim()) return payload.error.trim();
  } catch {
    // Fall back to status text below.
  }
  return `HTTP ${response.status}`;
}

async function fetchJson<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const fetcher = options.fetcher || globalThis.fetch;
  const response = await fetcher(`${API_BASE}${path}`, {
    credentials: "include",
    cache: "no-store",
    signal: options.signal,
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json() as Promise<T>;
}

export function nodeUiManifestPath(nodeId: string): string {
  return `/api/nodes/${encodeURIComponent(requireNodeId(nodeId))}/ui-manifest`;
}

export function nodeUiSurfaceDataPath(nodeId: string, endpoint: string): string {
  const corePath = readCoreEndpointPath(endpoint);
  return `/api/nodes/${encodeURIComponent(requireNodeId(nodeId))}/${corePath}`;
}

export async function fetchNodeUiManifest(
  nodeId: string,
  options: FetchOptions = {},
): Promise<NodeUiManifestFetchResponse> {
  return fetchJson<NodeUiManifestFetchResponse>(nodeUiManifestPath(nodeId), options);
}

export async function fetchNodeSurfaceData<T>(
  nodeId: string,
  endpoint: string,
  options: FetchOptions = {},
): Promise<T> {
  return fetchJson<T>(nodeUiSurfaceDataPath(nodeId, endpoint), options);
}
