export const LS_API_BASE_KEY = "hexe_api_base";
export const LEGACY_LS_API_BASE_KEY = "synthia_api_base";

export function defaultApiBase(): string {
  const host = window.location.hostname || "localhost";
  return `http://${host}:9001`;
}

export function getStoredApiBase(): string {
  const current = localStorage.getItem(LS_API_BASE_KEY);
  if (current) {
    return current;
  }
  const legacy = localStorage.getItem(LEGACY_LS_API_BASE_KEY);
  if (legacy) {
    localStorage.setItem(LS_API_BASE_KEY, legacy);
    return legacy;
  }
  return defaultApiBase();
}

export function setStoredApiBase(value: string): void {
  localStorage.setItem(LS_API_BASE_KEY, value);
}
