export function addonUiFrameSrc(addonId: string, backendBase?: string): string {
  const trimmed = String(addonId || "").trim();
  if (!trimmed) return "";
  const base = String(backendBase || "").trim().replace(/\/+$/, "");
  const path = `/ui/addons/${encodeURIComponent(trimmed)}`;
  return base ? `${base}${path}` : path;
}
