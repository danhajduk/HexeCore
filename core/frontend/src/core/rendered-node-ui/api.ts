import { API_BASE } from "../api/client";
import type { NodeUiAction, NodeUiManifestFetchResponse, NodeUiPageSnapshot } from "./types";

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

async function readJsonOrEmpty<T>(response: Response): Promise<T> {
  if (response.status === 204) return {} as T;
  const text = await response.text();
  if (!text.trim()) return {} as T;
  return JSON.parse(text) as T;
}

export function nodeUiManifestPath(nodeId: string): string {
  return `/api/nodes/${encodeURIComponent(requireNodeId(nodeId))}/ui-manifest`;
}

export function nodeUiSurfaceDataPath(nodeId: string, endpoint: string): string {
  const corePath = readCoreEndpointPath(endpoint);
  return `/api/nodes/${encodeURIComponent(requireNodeId(nodeId))}/${corePath}`;
}

export function nodeUiPageDataPath(nodeId: string, endpoint: string): string {
  return nodeUiSurfaceDataPath(nodeId, endpoint);
}

export function nodeUiActionPath(nodeId: string, endpoint: string): string {
  return nodeUiSurfaceDataPath(nodeId, endpoint);
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

export async function fetchNodePageData(
  nodeId: string,
  endpoint: string,
  options: FetchOptions = {},
): Promise<NodeUiPageSnapshot> {
  return fetchJson<NodeUiPageSnapshot>(nodeUiPageDataPath(nodeId, endpoint), options);
}

export async function executeNodeUiAction<T = Record<string, unknown>>(
  nodeId: string,
  action: Pick<NodeUiAction, "method" | "endpoint">,
  body?: unknown,
  options: FetchOptions = {},
): Promise<T> {
  const fetcher = options.fetcher || globalThis.fetch;
  const init: RequestInit = {
    method: action.method,
    credentials: "include",
    cache: "no-store",
    signal: options.signal,
  };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }

  const response = await fetcher(`${API_BASE}${nodeUiActionPath(nodeId, action.endpoint)}`, init);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return readJsonOrEmpty<T>(response);
}
