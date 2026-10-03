import { useEffect, useMemo, useState } from "react";
import "./settings.css";
import "./settings/admin-reload-card.css";

type Item = Record<string, any>;
type Snapshot = { households: Item[]; people: Item[]; users: Item[]; user_links: Item[]; guardians: Item[]; consents: Item[]; rooms: Item[]; endpoint_assignments: Item[]; lifecycle_requests: Item[] };
const empty: Snapshot = { households: [], people: [], users: [], user_links: [], guardians: [], consents: [], rooms: [], endpoint_assignments: [], lifecycle_requests: [] };
export const PEOPLE_IDENTITY_NOTICE = "User ≠ person.";

async function request(path: string, method = "GET", body?: unknown) {
  const response = await fetch(`/api/admin${path}`, { method, credentials: "include", headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined });
  if (!response.ok) { const payload = await response.json().catch(() => ({})); throw new Error(payload.detail || `Request failed (${response.status})`); }
  return response.json();
}

export default function SettingsPeople() {
  const [data, setData] = useState<Snapshot>(empty);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [password, setPassword] = useState("");
  const [householdName, setHouseholdName] = useState("");
  const [person, setPerson] = useState({ household_id: "", display_name: "", age_band: "unknown" });
  const [link, setLink] = useState({ person_id: "", user_id: "" });
  const [guardian, setGuardian] = useState({ guardian_person_id: "", dependent_person_id: "" });
  const [consent, setConsent] = useState({ person_id: "", purpose: "memory.read", decision: "granted" });
  const [room, setRoom] = useState({ household_id: "", display_name: "", audience_mode: "household" });
  const [assignment, setAssignment] = useState({ endpoint_id: "", room_id: "" });
  const activePeople = useMemo(() => data.people.filter((value) => value.status === "active"), [data.people]);
  const linkedPeople = new Set(data.user_links.map((value) => value.person_id));
  const linkedUsers = new Set(data.user_links.map((value) => value.user_id));

  async function load() { setError(""); try { setData(await request("/family")); } catch (value: any) { setError(value.message); } }
  async function mutate(path: string, body: unknown, method = "POST") { setBusy(true); setError(""); try { await request(path, method, body); await load(); } catch (value: any) { setError(value.message); } finally { setBusy(false); } }
  useEffect(() => { void load(); }, []);

  const options = (items: Item[], id: string, label: string) => items.map((value) => <option key={value[id]} value={value[id]}>{value[label]}</option>);
  return <div className="settings-page">
    <h1 className="settings-title">Settings / People</h1>
    <p className="settings-page-subtitle">Manage real people and households separately from login accounts.</p>
    <p className="settings-muted"><strong>{PEOPLE_IDENTITY_NOTICE}</strong> Users authenticate and hold platform roles. People represent household members and may exist without a login. Linking does not copy passwords, roles, sessions, or devices.</p>
    <section className="admin-card"><div className="admin-form">
      <label className="admin-label"><span className="admin-label-text">Confirm password for sensitive changes</span><input aria-label="Confirm password" type="password" className="admin-input" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
      {error && <div className="admin-error" role="alert">{error}</div>}
      <div className="admin-actions"><button className="admin-btn" onClick={() => void load()}>Refresh</button></div>
    </div></section>

    <section className="settings-section"><div className="settings-section-head"><h2>Households</h2><p>Policy boundaries containing people and rooms.</p></div><div className="admin-card admin-form">
      <input aria-label="Household name" className="admin-input" placeholder="Household name" value={householdName} onChange={(e) => setHouseholdName(e.target.value)} />
      <button className="admin-btn admin-btn-primary" disabled={busy || !householdName.trim()} onClick={() => void mutate("/family/households", { display_name: householdName }).then(() => setHouseholdName(""))}>Create household</button>
      {data.households.map((value) => <div className="admin-log" key={value.household_id}><strong>{value.display_name}</strong><div>{value.household_id} · {value.status}</div></div>)}
    </div></section>

    <section className="settings-section"><div className="settings-section-head"><h2>People</h2><p>Real household members; a login is optional.</p></div><div className="admin-card admin-form">
      <select aria-label="Person household" className="admin-input" value={person.household_id} onChange={(e) => setPerson({ ...person, household_id: e.target.value })}><option value="">Select household</option>{options(data.households, "household_id", "display_name")}</select>
      <input aria-label="Person display name" className="admin-input" placeholder="Display name" value={person.display_name} onChange={(e) => setPerson({ ...person, display_name: e.target.value })} />
      <select aria-label="Age band" className="admin-input" value={person.age_band} onChange={(e) => setPerson({ ...person, age_band: e.target.value })}>{["unknown", "adult", "teen", "child"].map((v) => <option key={v}>{v}</option>)}</select>
      <button className="admin-btn admin-btn-primary" disabled={busy || !person.household_id || !person.display_name.trim()} onClick={() => void mutate("/family/people", { ...person, reauth_password: password })}>Create person</button>
      {data.people.map((value) => <div className="admin-log" key={value.person_id}><strong>{value.display_name}</strong><div>{value.age_band || "age unspecified"} · {value.status} · {linkedPeople.has(value.person_id) ? "login linked" : "no login account"}</div>{value.status === "active" && <div className="admin-actions"><button className="admin-btn admin-btn-muted" onClick={() => void mutate(`/family/people/${encodeURIComponent(value.person_id)}`, { display_name: value.display_name, age_band: value.age_band, expected_version: value.version, archive: true, reauth_password: password }, "PUT")}>Archive</button><button className="admin-btn" onClick={() => void mutate("/family/lifecycle", { person_id: value.person_id, kind: "export", reauth_password: password })}>Request export</button><button className="admin-btn admin-btn-muted" onClick={() => void mutate("/family/lifecycle", { person_id: value.person_id, kind: "delete", reauth_password: password })}>Request deletion</button></div>}</div>)}
    </div></section>

    <section className="settings-section"><div className="settings-section-head"><h2>Login links</h2><p>One person may link to at most one user account, and vice versa.</p></div><div className="admin-card admin-form">
      <select aria-label="Link person" className="admin-input" value={link.person_id} onChange={(e) => setLink({ ...link, person_id: e.target.value })}><option value="">Select unlinked person</option>{options(activePeople.filter((v) => !linkedPeople.has(v.person_id)), "person_id", "display_name")}</select>
      <select aria-label="Link user" className="admin-input" value={link.user_id} onChange={(e) => setLink({ ...link, user_id: e.target.value })}><option value="">Select unlinked user</option>{options(data.users.filter((v) => !linkedUsers.has(v.user_id)), "user_id", "username")}</select>
      <button className="admin-btn admin-btn-primary" disabled={busy || !link.person_id || !link.user_id} onClick={() => void mutate("/family/user-links", { ...link, reauth_password: password })}>Link user and person</button>
      {data.user_links.map((value) => <div className="admin-log" key={value.person_id}>{activePeople.find((p) => p.person_id === value.person_id)?.display_name || value.person_id} ↔ {data.users.find((u) => u.user_id === value.user_id)?.username || value.user_id}<div className="admin-actions"><button className="admin-btn admin-btn-muted" onClick={() => void mutate(`/family/user-links/${encodeURIComponent(value.person_id)}`, { reauth_password: password }, "DELETE")}>Unlink</button></div></div>)}
    </div></section>

    <section className="settings-section"><div className="settings-section-head"><h2>Guardian authority and consent</h2><p>Relationships do not grant authority; these explicit scoped records do.</p></div><div className="admin-card admin-form">
      <select aria-label="Guardian" className="admin-input" value={guardian.guardian_person_id} onChange={(e) => setGuardian({ ...guardian, guardian_person_id: e.target.value })}><option value="">Guardian</option>{options(activePeople, "person_id", "display_name")}</select><select aria-label="Dependent" className="admin-input" value={guardian.dependent_person_id} onChange={(e) => setGuardian({ ...guardian, dependent_person_id: e.target.value })}><option value="">Dependent</option>{options(activePeople, "person_id", "display_name")}</select>
      <button className="admin-btn" disabled={busy || !guardian.guardian_person_id || !guardian.dependent_person_id} onClick={() => void mutate("/family/guardians", { ...guardian, purposes: ["memory.read", "memory.write", "export"], operations: ["memory.read", "memory.write", "export", "delete"], reauth_password: password })}>Add guardian authority</button>
      <select aria-label="Consent person" className="admin-input" value={consent.person_id} onChange={(e) => setConsent({ ...consent, person_id: e.target.value })}><option value="">Consent subject</option>{options(activePeople, "person_id", "display_name")}</select><select aria-label="Consent purpose" className="admin-input" value={consent.purpose} onChange={(e) => setConsent({ ...consent, purpose: e.target.value })}>{["memory.read", "memory.write", "personalization", "speaker-recognition", "model-training", "export"].map((v) => <option key={v}>{v}</option>)}</select><select aria-label="Consent decision" className="admin-input" value={consent.decision} onChange={(e) => setConsent({ ...consent, decision: e.target.value })}><option>granted</option><option>denied</option></select>
      <button className="admin-btn" disabled={busy || !consent.person_id} onClick={() => void mutate("/family/consents", { ...consent, visibility: ["private", "guardian_managed"], reauth_password: password })}>Record consent decision</button>
      {[...data.guardians, ...data.consents].map((value) => <div className="admin-log" key={value.relationship_id || value.consent_id}>{value.relationship_id ? `Guardian authority · ${value.status}` : `${value.purpose} · ${value.decision}`}</div>)}
    </div></section>

    <section className="settings-section"><div className="settings-section-head"><h2>Rooms and endpoints</h2><p>Room assignment provides context, never proof of who is present.</p></div><div className="admin-card admin-form">
      <select aria-label="Room household" className="admin-input" value={room.household_id} onChange={(e) => setRoom({ ...room, household_id: e.target.value })}><option value="">Select household</option>{options(data.households, "household_id", "display_name")}</select><input aria-label="Room name" className="admin-input" placeholder="Room name" value={room.display_name} onChange={(e) => setRoom({ ...room, display_name: e.target.value })}/><select aria-label="Room audience" className="admin-input" value={room.audience_mode} onChange={(e) => setRoom({ ...room, audience_mode: e.target.value })}><option>private</option><option>household</option><option>room</option></select><button className="admin-btn" disabled={busy || !room.household_id || !room.display_name} onClick={() => void mutate("/family/rooms", room)}>Create room</button>
      <input aria-label="Endpoint ID" className="admin-input" placeholder="Registered endpoint ID" value={assignment.endpoint_id} onChange={(e) => setAssignment({ ...assignment, endpoint_id: e.target.value })}/><select aria-label="Endpoint room" className="admin-input" value={assignment.room_id} onChange={(e) => setAssignment({ ...assignment, room_id: e.target.value })}><option value="">Select room</option>{options(data.rooms, "room_id", "display_name")}</select><button className="admin-btn" disabled={busy || !assignment.endpoint_id || !assignment.room_id} onClick={() => void mutate("/family/endpoint-assignments", assignment)}>Assign endpoint</button>
    </div></section>

    <section className="settings-section"><div className="settings-section-head"><h2>Lifecycle requests</h2><p>Deletion and export remain incomplete until required node receipts arrive.</p></div><div className="admin-card admin-form">{data.lifecycle_requests.map((value) => <div className="admin-log" key={value.request_id}><strong>{value.kind}</strong> · {value.state}<div>{value.request_id}</div></div>)}{!data.lifecycle_requests.length && <div className="admin-log">No pending lifecycle requests.</div>}</div></section>
  </div>;
}
