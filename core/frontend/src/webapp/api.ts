export type WebUser = { user_id: string; username: string; role: string; enabled: boolean };
export type WebSession = { session_id: string; device_id?: string | null; created_at: string; last_used_at: string; expires_at: string; revoked_at?: string | null };
export type WebDevice = { device_id: string; user_id?: string; display_name: string; platform?: string | null; enabled: boolean; last_seen_at?: string | null; notification_subscription_active?: boolean };

const ACCESS_KEY = "hexe.web.access";
const REFRESH_KEY = "hexe.web.refresh";

export function accessToken(): string { return sessionStorage.getItem(ACCESS_KEY) || ""; }
export function clearSession(): void { sessionStorage.removeItem(ACCESS_KEY); localStorage.removeItem(REFRESH_KEY); }
export function saveSession(access: string, refresh: string): void { sessionStorage.setItem(ACCESS_KEY, access); localStorage.setItem(REFRESH_KEY, refresh); }

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = accessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (response.status === 401 && localStorage.getItem(REFRESH_KEY)) {
    const refreshed = await fetch("/api/auth/user/refresh", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: localStorage.getItem(REFRESH_KEY) }) });
    if (refreshed.ok) {
      const value = await refreshed.json();
      saveSession(value.access_token, value.refresh_token);
      headers.set("Authorization", `Bearer ${value.access_token}`);
      response = await fetch(path, { ...init, headers, credentials: "same-origin" });
    }
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `request_failed_${response.status}`);
  return body as T;
}

export async function login(username: string, password: string, deviceId?: string): Promise<void> {
  const response = await fetch("/api/auth/user/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password, device_id: deviceId || null }) });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "login_failed");
  saveSession(body.access_token, body.refresh_token);
}
