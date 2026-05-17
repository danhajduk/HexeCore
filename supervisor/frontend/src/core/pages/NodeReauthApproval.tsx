import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import deniedImage from "../../assets/error.png";
import expiredImage from "../../assets/oops.png";
import presentingImage from "../../assets/presenting.png";
import successImage from "../../assets/success.png";
import workingImage from "../../assets/working.png";
import { useAdminSession } from "../auth/AdminSessionContext";
import { usePlatformBranding } from "../branding";
import "./onboarding-node-approval.css";

type ReauthSession = {
  session_id: string;
  session_state: string;
  node_id: string;
  node_name?: string | null;
  node_type?: string | null;
  node_software_version?: string | null;
  requested_node_type?: string | null;
  trust_status?: string | null;
  requested_hostname?: string | null;
  requested_ui_endpoint?: string | null;
  requested_api_base_url?: string | null;
  requested_from_ip?: string | null;
  reason?: string | null;
  created_at: string;
  expires_at: string;
  approved_at?: string | null;
  rejected_at?: string | null;
  approved_by_user_id?: string | null;
  rejection_reason?: string | null;
  final_payload_consumed_at?: string | null;
};

type PresenterState = "presenting" | "working" | "success" | "expired" | "denied";

function fmt(ts?: string | null): string {
  if (!ts) return "-";
  const n = Date.parse(ts);
  if (!Number.isFinite(n)) return ts;
  return new Date(n).toLocaleString();
}

function sessionStateLabel(value?: string | null): string {
  const state = String(value || "").trim();
  return state ? state.replace(/[_-]+/g, " ") : "unknown";
}

function maskSessionId(value?: string | null): string {
  const sessionId = String(value || "").trim();
  const tail = sessionId.slice(-4) || "----";
  return `************${tail}`;
}

async function readError(res: Response): Promise<string> {
  try {
    const payload = await res.json();
    if (typeof payload?.detail === "string" && payload.detail.trim()) return payload.detail.trim();
    if (typeof payload?.detail?.error === "string" && payload.detail.error.trim()) return payload.detail.error.trim();
    if (typeof payload?.error === "string" && payload.error.trim()) return payload.error.trim();
  } catch {
    // Fall through to status text.
  }
  return `HTTP ${res.status}`;
}

export default function NodeReauthApproval() {
  const { platformName } = usePlatformBranding();
  const { ready, authenticated, login } = useAdminSession();
  const [params] = useSearchParams();
  const rid = (params.get("rid") || params.get("sid") || "").trim();
  const state = (params.get("state") || "").trim();

  const [session, setSession] = useState<ReauthSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<"approve" | "reject" | null>(null);
  const [approvalWaitMsg, setApprovalWaitMsg] = useState<string | null>(null);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginErr, setLoginErr] = useState<string | null>(null);
  const [presenterState, setPresenterState] = useState<PresenterState>("presenting");
  const currentState = String(session?.session_state || "").trim().toLowerCase();

  const query = useMemo(() => {
    const q = new URLSearchParams();
    if (state) q.set("state", state);
    return q.toString();
  }, [state]);

  const presenter = useMemo(() => {
    const effectiveState: PresenterState = (() => {
      if (["rejected", "denied", "error"].includes(currentState)) return "denied";
      if (currentState === "expired") return "expired";
      if (currentState === "consumed") return "success";
      return presenterState;
    })();

    if (effectiveState === "denied") {
      return {
        image: deniedImage,
        alt: `${platformName} reporting a re-auth rejection`,
        eyebrow: "Re-auth denied",
        title: "Review required",
        copy: "This re-auth session was rejected or failed validation.",
      };
    }
    if (effectiveState === "expired") {
      return {
        image: expiredImage,
        alt: `${platformName} reporting an expired re-auth session`,
        eyebrow: "Session expired",
        title: "Approval window closed",
        copy: "This re-auth session expired before trust could be reissued.",
      };
    }
    if (effectiveState === "working") {
      return {
        image: workingImage,
        alt: `${platformName} processing node re-auth`,
        eyebrow: "Re-auth in progress",
        title: "Reissuing trust material",
        copy: "Core is validating approval state and waiting for the node to collect fresh credentials.",
      };
    }
    if (effectiveState === "success") {
      return {
        image: successImage,
        alt: `${platformName} re-auth completed successfully`,
        eyebrow: "Re-auth complete",
        title: "Trust reissued",
        copy: "The node collected new trust material and operational MQTT credentials.",
      };
    }
    return {
      image: presentingImage,
      alt: `${platformName} presenting the node re-auth card`,
      eyebrow: "Trust checkpoint",
      title: "Review before reissuing access",
      copy: "Approved re-auth sessions rotate node trust material and operational MQTT credentials.",
    };
  }, [currentState, platformName, presenterState]);

  function notifyParent(action: "approve" | "reject", sessionId: string) {
    try {
      if (window.opener && window.opener !== window) {
        window.opener.postMessage(
          {
            type: "hexe.node_reauth.decided",
            action,
            session_id: sessionId,
          },
          "*",
        );
      }
    } catch {
      // Ignore cross-window messaging issues; close path still proceeds.
    }
  }

  function closeApprovalWindow() {
    window.close();
    window.location.replace("/");
  }

  async function loadSession() {
    if (!ready || !authenticated || !rid) return;
    setLoading(true);
    setError(null);
    try {
      const suffix = query ? `?${query}` : "";
      const res = await fetch(`/api/system/nodes/reauth/sessions/${encodeURIComponent(rid)}${suffix}`, {
        credentials: "include",
        cache: "no-store",
      });
      if (!res.ok) throw new Error(await readError(res));
      const payload = await res.json();
      setSession((payload as { session?: ReauthSession }).session || null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setSession(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setPresenterState("presenting");
    void loadSession();
  }, [authenticated, query, ready, rid]);

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

  async function waitForReauthFinalization(sessionId: string): Promise<void> {
    const suffix = query ? `?${query}` : "";
    const deadline = Date.now() + 120_000;
    while (Date.now() < deadline) {
      const res = await fetch(`/api/system/nodes/reauth/sessions/${encodeURIComponent(sessionId)}${suffix}`, {
        credentials: "include",
        cache: "no-store",
      });
      if (!res.ok) throw new Error(await readError(res));
      const body = await res.json();
      const latest = (body as { session?: ReauthSession }).session || null;
      setSession(latest);
      if (String(latest?.session_state || "").toLowerCase() === "consumed") return;
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
    throw new Error("reauth_finalize_timeout");
  }

  async function decide(action: "approve" | "reject") {
    if (!session || actionBusy) return;
    setActionBusy(action);
    setActionError(null);
    setApprovalWaitMsg(null);
    if (action === "approve") setPresenterState("working");
    try {
      const suffix = query ? `?${query}` : "";
      const payload = action === "reject" ? { rejection_reason: "operator_rejected" } : undefined;
      const res = await fetch(`/api/system/nodes/reauth/sessions/${encodeURIComponent(session.session_id)}/${action}${suffix}`, {
        method: "POST",
        credentials: "include",
        headers: payload ? { "Content-Type": "application/json" } : undefined,
        body: payload ? JSON.stringify(payload) : undefined,
      });
      if (!res.ok) throw new Error(await readError(res));
      if (action === "approve") {
        setApprovalWaitMsg("Approval recorded. Waiting for node to collect new credentials...");
        await waitForReauthFinalization(session.session_id);
        setPresenterState("success");
        await new Promise((resolve) => setTimeout(resolve, 650));
      }
      notifyParent(action, session.session_id);
      closeApprovalWindow();
    } catch (e: unknown) {
      setPresenterState("presenting");
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setActionBusy(null);
      setApprovalWaitMsg(null);
    }
  }

  if (!rid || !state) {
    return (
      <section className="onboard-page">
        <div className="onboard-shell">
          <div className="onboard-header">
            <div className="onboard-eyebrow">Node Re-auth Approval</div>
            <p className="onboard-lead">Approved sessions rotate node trust material and operational MQTT credentials.</p>
          </div>
          <div className="onboard-error">Missing required `rid` or `state` in URL.</div>
        </div>
      </section>
    );
  }

  const canDecide = currentState === "pending" && actionBusy === null;

  return (
    <section className="onboard-page">
      <div className="onboard-shell">
        <div className="onboard-header">
          <div className="onboard-eyebrow">Node Re-auth Approval</div>
          <p className="onboard-lead">Approved sessions rotate node trust material and operational MQTT credentials.</p>
        </div>

        {!ready ? (
          <div className="onboard-status-card">
            <div className="onboard-meta">Checking admin session...</div>
          </div>
        ) : !authenticated ? (
          <div className="onboard-approval-layout onboard-approval-layout-login">
            <form className="onboard-login" onSubmit={submitLogin}>
              <div className="onboard-card-top">
                <div>
                  <div className="onboard-card-kicker">Admin sign-in required</div>
                  <h2 className="onboard-card-title">Core re-auth access</h2>
                </div>
                <div className="onboard-state-pill">Pending</div>
              </div>
              <div className="onboard-help">Sign in as Core admin to review and approve this re-auth request.</div>
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
              <button className="addon-btn addon-btn-primary onboard-action-primary" type="submit" disabled={loginBusy}>
                {loginBusy ? "Signing in..." : "Sign In"}
              </button>
              {loginErr && <div className="onboard-error">{loginErr}</div>}
            </form>

            <aside className="onboard-presenter-panel">
              <div className="onboard-presenter-copy">
                <div className="onboard-card-kicker">{presenter.eyebrow}</div>
                <h2 className="onboard-presenter-title">{presenter.title}</h2>
                <p className="onboard-lead onboard-presenter-lead">{presenter.copy}</p>
              </div>
              <div className="onboard-presenter-frame">
                <img className="onboard-presenter-image" src={presenter.image} alt={presenter.alt} />
              </div>
            </aside>
          </div>
        ) : loading ? (
          <div className="onboard-status-card">
            <div className="onboard-meta">Loading re-auth session...</div>
          </div>
        ) : error ? (
          <div className="onboard-error">{error}</div>
        ) : !session ? (
          <div className="onboard-error">Session not found.</div>
        ) : (
          <div className="onboard-approval-layout">
            <article className="onboard-card">
              <div className="onboard-card-top">
                <div>
                  <div className="onboard-card-kicker">Node Re-auth</div>
                  <h2 className="onboard-card-title">{session.node_name || session.node_id}</h2>
                  <div className="onboard-meta">Review the existing node identity before rotating trust material.</div>
                </div>
                <div className={`onboard-state-pill onboard-state-pill-${currentState || "unknown"}`}>
                  {sessionStateLabel(session.session_state)}
                </div>
              </div>

              <div className="onboard-card-sections">
                <section className="onboard-section">
                  <div className="onboard-section-title">Identity</div>
                  <div className="onboard-field-grid">
                    <div className="onboard-field">
                      <strong>Node ID</strong>
                      <span>{session.node_id}</span>
                    </div>
                    <div className="onboard-field">
                      <strong>Node Type</strong>
                      <span>{session.requested_node_type || session.node_type || "-"}</span>
                    </div>
                    <div className="onboard-field">
                      <strong>Version</strong>
                      <span>{session.node_software_version || "-"}</span>
                    </div>
                    <div className="onboard-field">
                      <strong>Trust Status</strong>
                      <span>{session.trust_status || "-"}</span>
                    </div>
                    <div className="onboard-field">
                      <strong>Hostname</strong>
                      <span>{session.requested_hostname || "-"}</span>
                    </div>
                    <div className="onboard-field">
                      <strong>API Base URL</strong>
                      <span>{session.requested_api_base_url || "-"}</span>
                    </div>
                  </div>
                </section>

                <section className="onboard-section">
                  <div className="onboard-section-title">Session</div>
                  <div className="onboard-field-grid">
                    <div className="onboard-field">
                      <strong>Session ID</strong>
                      <span>{maskSessionId(session.session_id)}</span>
                    </div>
                    <div className="onboard-field">
                      <strong>Status</strong>
                      <span>{sessionStateLabel(session.session_state)}</span>
                    </div>
                    <div className="onboard-field">
                      <strong>Created At</strong>
                      <span>{fmt(session.created_at)}</span>
                    </div>
                    <div className="onboard-field">
                      <strong>Expires At</strong>
                      <span>{fmt(session.expires_at)}</span>
                    </div>
                  </div>
                </section>

                <section className="onboard-section">
                  <div className="onboard-section-title">Connection</div>
                  <div className="onboard-field-grid onboard-field-grid-connection">
                    <div className="onboard-field">
                      <strong>IP Address</strong>
                      <span>{session.requested_from_ip || "-"}</span>
                    </div>
                    <div className="onboard-field">
                      <strong>Reason</strong>
                      <span>{session.reason || "-"}</span>
                    </div>
                  </div>
                </section>
              </div>

              <div className="onboard-actions">
                <button
                  className="addon-btn addon-btn-primary onboard-action-primary"
                  type="button"
                  disabled={!canDecide}
                  onClick={() => void decide("approve")}
                >
                  {actionBusy === "approve" ? approvalWaitMsg || "Approving..." : "Approve Re-auth"}
                </button>
                <button
                  className="addon-btn addon-btn-danger onboard-action-secondary"
                  type="button"
                  disabled={!canDecide}
                  onClick={() => void decide("reject")}
                >
                  {actionBusy === "reject" ? "Rejecting..." : "Reject"}
                </button>
              </div>

              {approvalWaitMsg && actionBusy === "approve" && <div className="onboard-meta">{approvalWaitMsg}</div>}
              {actionError && <div className="onboard-error">{actionError}</div>}
            </article>

            <aside className="onboard-presenter-panel">
              <div className="onboard-presenter-copy">
                <div className="onboard-card-kicker">{presenter.eyebrow}</div>
                <h2 className="onboard-presenter-title">{presenter.title}</h2>
                <p className="onboard-lead onboard-presenter-lead">{presenter.copy}</p>
                {presenterState === "success" && <div className="onboard-success-note">Re-auth complete. Closing this checkpoint now.</div>}
              </div>
              <div className="onboard-presenter-frame">
                <img className="onboard-presenter-image" src={presenter.image} alt={presenter.alt} />
              </div>
            </aside>
          </div>
        )}
      </div>
    </section>
  );
}
