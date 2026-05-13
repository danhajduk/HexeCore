export const RENDERED_NODE_UI_STORAGE_KEY = "hexe.renderedNodeUi.enabled";

export function parseRenderedNodeUiFlag(value: unknown): boolean | null {
  const text = String(value ?? "").trim().toLowerCase();
  if (!text) return null;
  if (["1", "true", "yes", "on", "enabled"].includes(text)) return true;
  if (["0", "false", "no", "off", "disabled"].includes(text)) return false;
  return null;
}

export function renderedNodeUiFeatureEnabled(
  envValue: unknown = (import.meta as any).env?.VITE_RENDERED_NODE_UI,
  storage: Pick<Storage, "getItem"> | null = typeof window !== "undefined" ? window.localStorage : null,
): boolean {
  const stored = storage ? parseRenderedNodeUiFlag(storage.getItem(RENDERED_NODE_UI_STORAGE_KEY)) : null;
  if (stored !== null) return stored;
  return parseRenderedNodeUiFlag(envValue) === true;
}
