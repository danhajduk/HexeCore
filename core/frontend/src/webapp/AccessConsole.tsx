import { useEffect, useMemo, useState } from "react";
import { api, clearSession, login, type WebDevice, type WebSession, type WebUser } from "./api";
import "./webapp.css";

type Bootstrap = { core: { core_name: string }; user: WebUser & { permissions: string[] }; device: WebDevice; notifications: { state: string } };
type Enrollment = { enrollment_id: string; proof: string; expires_at: string; public_hostname: string };

function message(error: unknown): string { return error instanceof Error ? error.message.replaceAll("_", " ") : "Request failed"; }
function date(value?: string | null): string { return value ? new Date(value).toLocaleString() : "Never"; }

export default function AccessConsole() {
  const [username, setUsername] = useState(""); const [password, setPassword] = useState("");
  const [boot, setBoot] = useState<Bootstrap | null>(null); const [needsDevice, setNeedsDevice] = useState(false);
  const [sessions, setSessions] = useState<WebSession[]>([]); const [devices, setDevices] = useState<WebDevice[]>([]);
  const [users, setUsers] = useState<WebUser[]>([]); const [allDevices, setAllDevices] = useState<WebDevice[]>([]);
  const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null); const [enrollmentState, setEnrollmentState] = useState("");
  const [newUser, setNewUser] = useState({ username: "", password: "", role: "member" });
  const [reauth, setReauth] = useState("");
  const canManage = useMemo(() => boot?.user.permissions.includes("users.manage") || (!boot && needsDevice), [boot, needsDevice]);

  async function load() {
    setError("");
    try {
      const value = await api<Bootstrap>("/api/web-app/bootstrap"); setBoot(value); setNeedsDevice(false);
      const [s, d] = await Promise.all([api<{items: WebSession[]}>("/api/auth/user/sessions"), api<{items: WebDevice[]}>("/api/auth/devices")]);
      setSessions(s.items); setDevices(d.items);
      if (value.user.permissions.includes("users.manage")) {
        const [u, a] = await Promise.all([api<{items: WebUser[]}>("/api/web-app/admin/users"), api<{items: WebDevice[]}>("/api/auth/devices/admin")]);
        setUsers(u.items); setAllDevices(a.items);
      }
    } catch (e) {
      if (message(e).includes("enrolled device required")) {
        setNeedsDevice(true);
        const u = await api<{items: WebUser[]}>("/api/web-app/admin/users").catch(() => ({ items: [] })); setUsers(u.items);
      } else setError(message(e));
    }
  }
  useEffect(() => { void load(); }, []);

  async function signIn(event: React.FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { await login(username, password); setPassword(""); await load(); } catch (e) { setError(message(e)); } finally { setBusy(false); } }
  async function act(action: () => Promise<unknown>, done: string) { setBusy(true); setError(""); setNotice(""); try { await action(); setNotice(done); await load(); } catch (e) { setError(message(e)); } finally { setBusy(false); } }
  async function createEnrollment() {
    const response = await api<{enrollment: Enrollment}>("/api/auth/device-enrollments", { method: "POST", body: JSON.stringify({ display_name: "Mobile browser", ttl_seconds: 600 }) });
    setEnrollment(response.enrollment); setEnrollmentState("pending");
  }
  const deepLink = enrollment ? `https://${enrollment.public_hostname}/app/enroll?enrollment_id=${encodeURIComponent(enrollment.enrollment_id)}&proof=${encodeURIComponent(enrollment.proof)}` : "";

  if (!boot && !needsDevice) return <main className="webapp"><section className="login-card"><h1>Hexe</h1><p>Sign in to your Core.</p><form onSubmit={signIn}><label>Username<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} /></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} /></label><button disabled={busy}>Sign in</button></form>{error && <p role="alert" className="error">{error}</p>}</section></main>;

  return <main className="webapp">
    <header><div><span className="eyebrow">Mobile access</span><h1>{boot?.core.core_name || "Hexe Core"}</h1></div><button className="secondary" onClick={()=>{clearSession(); location.assign("/app");}}>Sign out</button></header>
    {error && <p role="alert" className="banner error">{error}</p>}{notice && <p role="status" className="banner ok">{notice}</p>}
    {needsDevice && <section><h2>Enroll this device</h2><p>Your identity is valid. An owner must explicitly approve this browser before the app can open.</p><button disabled={busy} onClick={()=>void act(createEnrollment,"Enrollment created")}>Create 10-minute enrollment</button>{enrollment && <div className="stack"><code className="deep-link">{deepLink}</code><button onClick={()=>void navigator.clipboard.writeText(deepLink)}>Copy deep link</button><button onClick={()=>void act(async()=>{ await api(`/api/auth/device-enrollments/${enrollment.enrollment_id}/approve`,{method:"POST"}); setEnrollmentState("approved"); },"Enrollment approved")}>Approve</button><button className="secondary" onClick={()=>void act(async()=>{const s=await api<{status:string}>(`/api/auth/device-enrollments/${enrollment.enrollment_id}`);setEnrollmentState(s.status);},"State refreshed")}>Refresh state</button><strong>Status: {enrollmentState}</strong></div>}</section>}
    {boot && <>
      <section><h2>Your access</h2><div className="facts"><span>{boot.user.username}</span><span>{boot.user.role}</span><span>Push: {boot.notifications.state}</span></div></section>
      <section><h2>Sessions</h2><div className="cards">{sessions.map(s=><article key={s.session_id}><strong>{s.session_id.slice(0,12)}…</strong><small>Last used {date(s.last_used_at)}</small><button className="danger" disabled={busy} onClick={()=>void act(()=>api(`/api/auth/user/sessions/${s.session_id}`,{method:"DELETE"}),"Session revoked")}>Revoke</button></article>)}</div></section>
      <section><h2>Devices & notifications</h2><div className="cards">{devices.map(d=><article key={d.device_id}><strong>{d.display_name}</strong><small>{d.platform || "Browser"} · seen {date(d.last_seen_at)}</small>{d.device_id===boot.device.device_id && <><button onClick={()=>void act(()=>api("/api/web-app/notifications/test",{method:"POST"}),"Test notification queued")}>Send test</button><button onClick={()=>void act(()=>api(`/api/auth/devices/${d.device_id}/notification-preferences`,{method:"PUT",body:JSON.stringify({enabled:true,privacy_level:"generic",time_zone:Intl.DateTimeFormat().resolvedOptions().timeZone,categories:{security:true,"approval-required":true,"task-completion":true,"timers-reminders":true,"device-health":true,"email-alerts":false},severity_threshold:"info"})}),"Preferences saved")}>Enable safe notifications</button></>}<button className="danger" onClick={()=>void act(()=>api(`/api/auth/devices/${d.device_id}`,{method:"DELETE"}),"Device revoked")}>Revoke</button></article>)}</div></section>
    </>}
    {canManage && <section><h2>People & installed devices</h2><p>Role, disable, and deletion changes require your password again. The last enabled owner cannot be removed.</p><div className="inline-form"><input aria-label="New username" placeholder="Username" value={newUser.username} onChange={e=>setNewUser({...newUser,username:e.target.value})}/><input aria-label="Temporary password" type="password" placeholder="Temporary password" value={newUser.password} onChange={e=>setNewUser({...newUser,password:e.target.value})}/><select aria-label="Role" value={newUser.role} onChange={e=>setNewUser({...newUser,role:e.target.value})}><option>member</option><option>guest</option><option>admin</option><option>owner</option></select><button onClick={()=>void act(()=>api("/api/web-app/admin/users",{method:"POST",body:JSON.stringify({...newUser,enabled:true})}),"User created")}>Invite user</button></div><label className="reauth">Confirm your password for sensitive changes<input type="password" value={reauth} onChange={e=>setReauth(e.target.value)}/></label><div className="cards">{users.map(u=><article key={u.user_id}><strong>{u.username}</strong><small>{u.role} · {u.enabled?"enabled":"disabled"}</small><button disabled={!reauth} onClick={()=>void act(()=>api("/api/web-app/admin/users",{method:"POST",body:JSON.stringify({username:u.username,role:u.role,enabled:!u.enabled,reauth_password:reauth})}),u.enabled?"User disabled":"User enabled")}>{u.enabled?"Disable":"Enable"}</button><button className="danger" disabled={!reauth} onClick={()=>void act(()=>api(`/api/web-app/admin/users/${encodeURIComponent(u.username)}`,{method:"DELETE",body:JSON.stringify({reauth_password:reauth})}),"User deleted")}>Delete</button></article>)}</div><h3>All installed devices</h3><div className="cards">{allDevices.map(d=><article key={d.device_id}><strong>{d.display_name}</strong><small>User {d.user_id} · {d.enabled?"enabled":"disabled"} · push {d.notification_subscription_active?"ready":"not registered"}</small><button className="danger" onClick={()=>void act(()=>api(`/api/auth/devices/admin/${d.device_id}`,{method:"DELETE"}),"Device revoked")}>Revoke</button></article>)}</div></section>}
  </main>;
}
