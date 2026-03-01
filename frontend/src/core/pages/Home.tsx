import { useState } from "react";

import { useAdminSession } from "../auth/AdminSessionContext";
import "./home.css";

export default function Home() {
  const { authenticated, login, logout, ready } = useAdminSession();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submitLogin() {
    if (!username.trim() || !password) {
      setErr("username_and_password_required");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const result = await login(username.trim(), password);
      if (!result.ok) {
        setErr(result.error || "login_failed");
        return;
      }
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  async function submitLogout() {
    setBusy(true);
    setErr(null);
    try {
      await logout();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="home-title">Home</h1>
      <p>Core shell is running. If you synced addons, they will appear in the sidebar.</p>

      <section className="home-auth-card">
        <div className="home-auth-title">Admin Access</div>
        {!ready ? (
          <div>Checking session...</div>
        ) : authenticated ? (
          <>
            <div className="home-auth-ok">Admin session is active.</div>
            <button className="home-auth-btn" onClick={submitLogout} disabled={busy}>
              {busy ? "Signing out..." : "Sign out"}
            </button>
          </>
        ) : (
          <>
            <div className="home-auth-help">Sign in with your admin username and password to unlock all routes.</div>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              className="home-auth-input"
            />
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              type="password"
              className="home-auth-input"
            />
            <button className="home-auth-btn" onClick={submitLogin} disabled={busy || !username.trim() || !password}>
              {busy ? "Signing in..." : "Sign in as Admin"}
            </button>
          </>
        )}
        {err && <div className="home-auth-err">{err}</div>}
      </section>
    </div>
  );
}
