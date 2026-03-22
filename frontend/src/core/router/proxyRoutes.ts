export function addonUiProxyPath(addonId: string, path?: string): string {
  const safeAddonId = encodeURIComponent(String(addonId || "").trim());
  if (!safeAddonId) return "";
  const cleanPath = String(path || "").trim().replace(/^\/+/, "");
  return cleanPath ? `/addons/${safeAddonId}/${cleanPath}` : `/addons/${safeAddonId}/`;
}

export function nodeUiProxyPath(nodeId: string, path?: string): string {
  const safeNodeId = encodeURIComponent(String(nodeId || "").trim());
  if (!safeNodeId) return "";
  const cleanPath = String(path || "").trim().replace(/^\/+/, "");
  return cleanPath ? `/nodes/${safeNodeId}/ui/${cleanPath}` : `/nodes/${safeNodeId}/ui/`;
}
