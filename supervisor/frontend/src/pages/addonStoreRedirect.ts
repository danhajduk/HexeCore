export type UiRedirectPayload = {
  ui_reachable?: boolean | null;
  ui_redirect_target?: string | null;
};

export function resolveUiRedirectTarget(payload: UiRedirectPayload | null | undefined, addonId: string): string | null {
  if (!payload) return null;
  const candidate = typeof payload.ui_redirect_target === "string" ? payload.ui_redirect_target.trim() : "";
  if (candidate) return candidate;
  if (payload.ui_reachable) return `/addons/${addonId}`;
  return null;
}

export function standaloneUiFallbackMessage(addonId: string): string {
  return `Install completed, but addon UI for '${addonId}' is not reachable yet. Stay on Store and open it later from Addons.`;
}
