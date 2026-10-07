export type WebUser = { user_id: string; username: string; role: string; enabled: boolean };
export type WebSession = { session_id: string; device_id?: string | null; created_at: string; last_used_at: string; expires_at: string; revoked_at?: string | null };
export type WebDevice = { device_id: string; user_id?: string; display_name: string; platform?: string | null; enabled: boolean; last_seen_at?: string | null; notification_subscription_active?: boolean };

const ACCESS_KEY = "hexe.web.access";
const REFRESH_KEY = "refresh";
const DEVICE_ID_KEY = "device-id";
const UNLOCKED_KEY = "hexe.web.unlocked";
const DEVICE_LOGIN_VERSION = "hexe.web-app-device-login.v1";
let refreshPromise: Promise<string | null> | null = null;

async function credentials<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T>): Promise<T | undefined> {
  const db=await new Promise<IDBDatabase>((resolve,reject)=>{const request=indexedDB.open("hexe-web-app",2);request.onupgradeneeded=()=>{if(!request.result.objectStoreNames.contains("credentials"))request.result.createObjectStore("credentials");if(!request.result.objectStoreNames.contains("device-keys"))request.result.createObjectStore("device-keys");};request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
  try{return await new Promise<T|undefined>((resolve,reject)=>{const request=action(db.transaction("credentials",mode).objectStore("credentials"));request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});}finally{db.close();}
}

export function accessToken(): string { return sessionStorage.getItem(ACCESS_KEY) || ""; }
export function sessionUnlocked(): boolean { return sessionStorage.getItem(UNLOCKED_KEY) === "1"; }
export function discardAccessToken(): void { sessionStorage.removeItem(ACCESS_KEY); sessionStorage.removeItem(UNLOCKED_KEY); }
async function clearLocalSession(): Promise<void> { discardAccessToken(); await credentials("readwrite",store=>store.delete(REFRESH_KEY)); }
export async function clearSession(): Promise<void> {
  const token=accessToken();
  try { if(token)await fetch("/api/auth/user/logout",{method:"POST",headers:{Authorization:`Bearer ${token}`}}); }
  finally { await clearLocalSession(); }
}
export async function saveSession(access: string, refresh: string): Promise<void> { sessionStorage.setItem(ACCESS_KEY, access); sessionStorage.setItem(UNLOCKED_KEY,"1"); await credentials("readwrite",store=>store.put(refresh,REFRESH_KEY)); }
export async function rememberEnrolledDevice(deviceId: string): Promise<void> { await credentials("readwrite",store=>store.put(deviceId,DEVICE_ID_KEY)); }

export async function enrolledDeviceId(): Promise<string | null> {
  const saved=await credentials<string>("readonly",store=>store.get(DEVICE_ID_KEY));
  if(saved)return saved;
  const db=await new Promise<IDBDatabase>((resolve,reject)=>{const request=indexedDB.open("hexe-web-app",2);request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
  try {
    const keys=await new Promise<IDBValidKey[]>((resolve,reject)=>{const request=db.transaction("device-keys","readonly").objectStore("device-keys").getAllKeys();request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
    const migrated=keys.length===1?String(keys[0]):null;
    if(migrated)await rememberEnrolledDevice(migrated);
    return migrated;
  } finally { db.close(); }
}

async function installationKey(deviceId: string): Promise<CryptoKey | null> {
  const db=await new Promise<IDBDatabase>((resolve,reject)=>{const request=indexedDB.open("hexe-web-app",2);request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
  try{return await new Promise<CryptoKey|null>((resolve,reject)=>{const request=db.transaction("device-keys","readonly").objectStore("device-keys").get(deviceId);request.onsuccess=()=>resolve(request.result||null);request.onerror=()=>reject(request.error);});}finally{db.close();}
}

const b64url=(bytes:ArrayBuffer)=>btoa(String.fromCharCode(...new Uint8Array(bytes))).replaceAll("+","-").replaceAll("/","_").replace(/=+$/,"");
const fromB64url=(value:string)=>Uint8Array.from(atob(value.replaceAll("-","+").replaceAll("_","/")+"=".repeat((4-value.length%4)%4)),char=>char.charCodeAt(0));
function publicKeyCredentialJSON(value: PublicKeyCredential): Record<string, unknown> {
  const response=value.response as AuthenticatorAssertionResponse|AuthenticatorAttestationResponse;
  return {id:value.id,rawId:b64url(value.rawId),type:value.type,authenticatorAttachment:value.authenticatorAttachment,response:{clientDataJSON:b64url(response.clientDataJSON),...("attestationObject" in response?{attestationObject:b64url(response.attestationObject),transports:response.getTransports?.()}:{authenticatorData:b64url(response.authenticatorData),signature:b64url(response.signature),userHandle:response.userHandle?b64url(response.userHandle):null})}};
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  refreshPromise=(async()=>{
    const refreshToken=await credentials<string>("readonly",store=>store.get(REFRESH_KEY));
    if(!refreshToken){await clearLocalSession();return null;}
    const response=await fetch("/api/auth/user/refresh",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({refresh_token:refreshToken})});
    if(!response.ok){await clearLocalSession();return null;}
    const value=await response.json(); await saveSession(value.access_token,value.refresh_token); return String(value.access_token);
  })().finally(()=>{refreshPromise=null;});
  return refreshPromise;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = accessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (response.status === 401) {
    const refreshedToken=await refreshAccessToken();
    if (refreshedToken) {
      headers.set("Authorization", `Bearer ${refreshedToken}`);
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

export async function loginEnrolledDevice(username: string, password: string): Promise<void> {
  const deviceId=await enrolledDeviceId();
  if(!deviceId){await login(username,password);return;}
  const key=await installationKey(deviceId);
  if(!key)throw new Error("enrolled_device_key_missing");
  const challengeResponse=await fetch("/api/auth/user/device-login/challenge",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({device_id:deviceId,...(username&&password?{username,password}:{})})});
  const challenge=await challengeResponse.json().catch(()=>({}));
  if(!challengeResponse.ok)throw new Error(typeof challenge.detail==="string"?challenge.detail:"device_login_failed");
  const message=`${DEVICE_LOGIN_VERSION}:${challenge.core_id}:${challenge.challenge_id}:${challenge.nonce}:${deviceId}`;
  const signature=b64url(await crypto.subtle.sign("Ed25519",key,new TextEncoder().encode(message)));
  if(!window.PublicKeyCredential)throw new Error("passkey_unavailable");
  const credential=challenge.passkey_registration_required
    ? await navigator.credentials.create({publicKey:{...challenge.registration_options,challenge:fromB64url(challenge.registration_options.challenge),user:{...challenge.registration_options.user,id:fromB64url(challenge.registration_options.user.id)}}}) as PublicKeyCredential|null
    : await navigator.credentials.get({publicKey:{challenge:fromB64url(challenge.nonce),rpId:location.hostname,allowCredentials:[{type:"public-key",id:fromB64url(challenge.credential_id)}],userVerification:"required",timeout:120000}}) as PublicKeyCredential|null;
  if(!credential)throw new Error("passkey_cancelled");
  const response=await fetch("/api/auth/user/device-login/complete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({challenge_id:challenge.challenge_id,signature,passkey_credential:publicKeyCredentialJSON(credential)})});
  const body=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(typeof body.detail==="string"?body.detail:"device_login_failed");
  await saveSession(body.access_token,body.refresh_token);
}

export async function createPasskey(options:any): Promise<Record<string,unknown>> {
  if(!window.PublicKeyCredential)throw new Error("passkey_unavailable");
  const credential=await navigator.credentials.create({publicKey:{...options,challenge:fromB64url(options.challenge),user:{...options.user,id:fromB64url(options.user.id)}}}) as PublicKeyCredential|null;
  if(!credential)throw new Error("passkey_cancelled");
  return publicKeyCredentialJSON(credential);
}

export async function logout(): Promise<void> {
  await clearSession();
}
