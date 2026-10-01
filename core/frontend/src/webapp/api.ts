export type WebUser = { user_id: string; username: string; role: string; enabled: boolean };
export type WebSession = { session_id: string; device_id?: string | null; created_at: string; last_used_at: string; expires_at: string; revoked_at?: string | null };
export type WebDevice = { device_id: string; user_id?: string; display_name: string; platform?: string | null; enabled: boolean; last_seen_at?: string | null; notification_subscription_active?: boolean };

const ACCESS_KEY = "hexe.web.access";
const REFRESH_KEY = "refresh";

async function credentials<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T>): Promise<T | undefined> {
  const db=await new Promise<IDBDatabase>((resolve,reject)=>{const request=indexedDB.open("hexe-web-app",2);request.onupgradeneeded=()=>{if(!request.result.objectStoreNames.contains("credentials"))request.result.createObjectStore("credentials");if(!request.result.objectStoreNames.contains("device-keys"))request.result.createObjectStore("device-keys");};request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
  try{return await new Promise<T|undefined>((resolve,reject)=>{const request=action(db.transaction("credentials",mode).objectStore("credentials"));request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});}finally{db.close();}
}

export function accessToken(): string { return sessionStorage.getItem(ACCESS_KEY) || ""; }
export async function clearSession(): Promise<void> { sessionStorage.removeItem(ACCESS_KEY); await credentials("readwrite",store=>store.delete(REFRESH_KEY)); }
export async function saveSession(access: string, refresh: string): Promise<void> { sessionStorage.setItem(ACCESS_KEY, access); await credentials("readwrite",store=>store.put(refresh,REFRESH_KEY)); }

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = accessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  const refreshToken=response.status===401?await credentials<string>("readonly",store=>store.get(REFRESH_KEY)):undefined;
  if (response.status === 401 && refreshToken) {
    const refreshed = await fetch("/api/auth/user/refresh", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: refreshToken }) });
    if (refreshed.ok) {
      const value = await refreshed.json();
      await saveSession(value.access_token, value.refresh_token);
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
  await saveSession(body.access_token, body.refresh_token);
}
