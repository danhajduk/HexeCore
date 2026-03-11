import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useAdminSession } from "../auth/AdminSessionContext";
import "./onboarding-node-approval.css";

type ApprovalSession = {
  session_id: string;
  session_state: string;
  requested_node_name: string;
  requested_node_type: string;
  requested_node_software_version: string;
  requested_hostname?: string | null;
  requested_from_ip?: string | null;
  created_at: string;
  expires_at: string;
  approved_at?: string | null;
  rejected_at?: string | null;
  approved_by_user_id?: string | null;
  rejection_reason?: string | null;
  linked_node_id?: string | null;
  final_payload_consumed_at?: string | null;
};

function fmt(ts?: string | null): string {
  if (!ts) return "-";
  const n = Date.parse(ts);
  if (!Number.isFinite(n)) return ts;
  return new Date(n).toLocaleString();
}

export default function OnboardingNodeApproval() {
  const { ready, authenticated, login } = useAdminSession();
  const [params] = useSearchParams();
  const sid = (params.get("sid") || "").trim();
  const state = (params.get("state") || "").trim();

  const [session, setSession] = useState<ApprovalSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<"approve" | "reject" | null>(null);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginErr, setLoginErr] = useState<string | null>(null);

  const query = useMemo(() => {
    const q = new URLSearchParams();
    if (state) q.set("state", state);
    return q.toString();
  }, [state]);

  async function loadSession() {
    if (!ready || !authenticated || !sid) return;
    setLoading(true);
    setError(null);
    try {
      const suffix = query ? `?${query}` : "";
      const res = await fetch(`/api/system/nodes/onboarding/sessions/${encodeURIComponent(sid)}${suffix}`, {
        credentials: "include",
        cache: "no-store",
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = typeof payload?.detail === "string" ? payload.detail : payload?.detail?.error || `HTTP ${res.status}`;
        throw new Error(detail);
      }
      setSession((payload as { session?: ApprovalSession }).session || null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setSession(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSession();
  }, [authenticated, query, ready, sid]);

  async function submitLogin(e: FormEvent) {
    e.preventDefault();
    if (loginBusy) return;
    setLoginBusy(true);
    setLoginErr(null);
    try {
      const result = await login(username.trim(), password);
      if (!result.ok) {
        setLoginErr(result.error || "login_failed");
        return;
      }
      setPassword("");
    } finally {
      setLoginBusy(false);
    }
  }

  async function decide(action: "approve" | "reject") {
    if (!session || actionBusy) return;
    setActionBusy(action);
    setActionError(null);
    try {
      const suffix = query ? `?${query}` : "";
      const payload = action === "reject" ? { rejection_reason: "operator_rejected" } : undefined;
      const res = await fetch(
        `/api/system/nodes/onboarding/sessions/${encodeURIComponent(session.session_id)}/${action}${suffix}`,
        {
          method: "POST",
          credentials: "include",
          headers: payload ? { "Content-Type": "application/json" } : undefined,
          body: payload ? JSON.stringify(payload) : undefined,
        },
      );
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = typeof body?.detail === "string" ? body.detail : body?.detail?.error || `HTTP ${res.status}`;
        throw new Error(detail);
      }
      await loadSession();
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setActionBusy(null);
    }
  }

  if (!sid) {
    return (
      <section className="onboard-page">
        <h1>Node Onboarding Approval</h1>
        <div className="onboard-error">Missing required `sid` in URL.</div>
      </section>
    );
  }

  return (
    <section className="onboard-page">
      <h1>Node Onboarding Approval</h1>
      {!ready ? (
        <div className="onboard-meta">Checking admin session...</div>
      ) : !authenticated ? (
        <form className="onboard-login" onSubmit={submitLogin}>
          <div className="onboard-help">Sign in as Core admin to review and decide this onboarding request.</div>
          <label>
            <span>Username</span>
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <label>
            <span>Password</span>
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              autoComplete="current-password"
            />
          </label>
          <button type="submit" disabled={loginBusy}>{loginBusy ? "Signing in..." : "Sign In"}</button>
          {loginErr && <div className="onboard-error">{loginErr}</div>}
        </form>
      ) : loading ? (
        <div className="onboard-meta">Loading onboarding session...</div>
      ) : error ? (
        <div className="onboard-error">{error}</div>
      ) : !session ? (
        <div className="onboard-error">Session not found.</div>
      ) : (
        <div className="onboard-card">
          <div className="onboard-grid">
            <div><strong>Session</strong><span>{session.session_id}</span></div>
            <div><strong>State</strong><span>{session.session_state}</span></div>
            <div><strong>Node Name</strong><span>{session.requested_node_name}</span></div>
            <div><strong>Node Type</strong><span>{session.requested_node_type}</span></div>
            <div><strong>Version</strong><span>{session.requested_node_software_version}</span></div>
            <div><strong>Hostname</strong><span>{session.requested_hostname || "-"}</span></div>
            <div><strong>Source IP</strong><span>{session.requested_from_ip || "-"}</span></div>
            <div><strong>Created</strong><span>{fmt(session.created_at)}</span></div>
            <div><strong>Expires</strong><span>{fmt(session.expires_at)}</span></div>
          </div>
          <div className="onboard-actions">
            <button
              type="button"
              disabled={session.session_state !== "pending" || actionBusy !== null}
              onClick={() => void decide("approve")}
            >
              {actionBusy === "approve" ? "Approving..." : "Approve"}
            </button>
            <button
              type="button"
              disabled={session.session_state !== "pending" || actionBusy !== null}
              onClick={() => void decide("reject")}
            >
              {actionBusy === "reject" ? "Rejecting..." : "Reject"}
            </button>
          </div>
          {actionError && <div className="onboard-error">{actionError}</div>}
        </div>
      )}
    </section>
  );
}
