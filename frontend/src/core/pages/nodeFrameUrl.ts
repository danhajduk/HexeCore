export function nodeUiFrameSrc(nodeId: string, rawEndpoint?: string | null, rawHost?: string | null): string {
  const safeNodeId = String(nodeId || "").trim();
  if (!safeNodeId) return "";
  const endpoint = String(rawEndpoint || "").trim();
  if (endpoint) {
    return /^https?:\/\//i.test(endpoint) ? `/ui/nodes/${encodeURIComponent(safeNodeId)}` : "";
  }
  const host = String(rawHost || "").trim();
  if (!host) return "";
  return `/ui/nodes/${encodeURIComponent(safeNodeId)}`;
}
