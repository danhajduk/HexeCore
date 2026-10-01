import { useMemo, useState } from "react";
import { saveSession } from "./api";
import "./webapp.css";

const b64url = (bytes: ArrayBuffer) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");

async function keepKey(id: string, key: CryptoKey): Promise<void> {
  const db = await new Promise<IDBDatabase>((resolve, reject) => { const request = indexedDB.open("hexe-web-app", 1); request.onupgradeneeded=()=>request.result.createObjectStore("device-keys"); request.onsuccess=()=>resolve(request.result); request.onerror=()=>reject(request.error); });
  await new Promise<void>((resolve, reject) => { const tx=db.transaction("device-keys","readwrite"); tx.objectStore("device-keys").put(key,id); tx.oncomplete=()=>resolve(); tx.onerror=()=>reject(tx.error); });
  db.close();
}

export default function EnrollmentPage() {
  const query = useMemo(()=>new URLSearchParams(location.search),[]); const enrollmentId=query.get("enrollment_id")||""; const proof=query.get("proof")||"";
  const [state,setState]=useState("Ready to bind this browser after owner approval."); const [busy,setBusy]=useState(false);
  async function complete() {
    setBusy(true);
    try {
      if (!enrollmentId || !proof) throw new Error("Enrollment link is incomplete.");
      const pair = await crypto.subtle.generateKey({name:"Ed25519"},true,["sign","verify"]) as CryptoKeyPair;
      const deviceId=`web_${crypto.randomUUID().replaceAll("-","")}`;
      const publicKey=b64url(await crypto.subtle.exportKey("raw",pair.publicKey));
      const privateBytes=await crypto.subtle.exportKey("pkcs8",pair.privateKey);
      const deviceKey=await crypto.subtle.importKey("pkcs8",privateBytes,{name:"Ed25519"},false,["sign"]);
      const message=new TextEncoder().encode(`hexe.web-app-enrollment.v1:${location.hostname.split(".")[0]}:${enrollmentId}:${deviceId}`);
      const signature=b64url(await crypto.subtle.sign("Ed25519",deviceKey,message));
      const response=await fetch(`/api/auth/device-enrollments/${encodeURIComponent(enrollmentId)}/complete`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({proof,device_id:deviceId,public_key:publicKey,signature,platform:navigator.platform||"web",browser_metadata:{browser_name:navigator.userAgent.slice(0,80)}})});
      const body=await response.json().catch(()=>({})); if(!response.ok) throw new Error(String(body.detail||`Request failed (${response.status})`).replaceAll("_"," "));
      await keepKey(deviceId,deviceKey); saveSession(body.access_token,body.refresh_token); history.replaceState({},"","/app"); location.assign("/app");
    } catch(error) { setState(error instanceof Error?error.message:"Enrollment failed"); } finally { setBusy(false); }
  }
  return <main className="webapp"><section className="login-card"><span className="eyebrow">Secure device enrollment</span><h1>Add this browser</h1><p>{state}</p><p>The link expires quickly and works only once. Ask a Core owner to approve it, then continue here.</p><button disabled={busy||!enrollmentId||!proof} onClick={()=>void complete()}>{busy?"Binding…":"Complete enrollment"}</button><a className="text-link" href="/app">Return to sign in</a></section></main>;
}
