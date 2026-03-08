import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useAdminSession } from "../auth/AdminSessionContext";
import "./home.css";

type AddonSummary = {
  id: string;
  name?: string;
  version?: string;
  enabled?: boolean;
  health_status?: string;
  discovery_source?: string;
  updated_at?: string | null;
};

type ServiceStatus = {
  running: boolean;
  active_state?: string;
  available?: boolean;
};

type SystemStats = {
  timestamp: number;
  hostname: string;
  uptime_s: number;
  cpu: { percent_total: number };
  mem: { percent: number };
  disks: Record<string, { percent: number }>;
  services?: Record<string, ServiceStatus>;
  busy_rating: number;
};

type RepoStatus = {
  ok: boolean;
  update_available?: boolean;
  status?: string;
};

type EventItem = {
  id: string;
  event_type: string;
  timestamp: string;
  source: string;
  payload?: Record<string, unknown>;
};

type SchedulerStatus = {
  snapshot?: {
    active_leases: number;
    queue_depths: Record<string, number>;
  };
};

type MqttStatus = {
  ok?: boolean;
  connected?: boolean;
  enabled?: boolean;
};

function fmtUptime(sec: number): string {
  const h = sec / 3600;
  if (h < 48) return `${h.toFixed(1)}h`;
  const d = Math.floor(h / 24);
  const rem = h - d * 24;
  return `${d}d ${rem.toFixed(0)}h`;
}

function pct(value: number): string {
  return `${Math.max(0, Math.min(100, value)).toFixed(1)}%`;
}

function relative(ts: string): string {
  const t = Date.parse(ts);
  if (!Number.isFinite(t)) return ts;
  const deltaS = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (deltaS < 60) return `${deltaS}s ago`;
  if (deltaS < 3600) return `${Math.floor(deltaS / 60)}m ago`;
  if (deltaS < 86400) return `${Math.floor(deltaS / 3600)}h ago`;
  return `${Math.floor(deltaS / 86400)}d ago`;
}

export default function Home() {
  const { authenticated, login, logout, ready } = useAdminSession();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [addons, setAddons] = useState<AddonSummary[]>([]);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [repoStatus, setRepoStatus] = useState<RepoStatus | null>(null);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [mqtt, setMqtt] = useState<MqttStatus | null>(null);
  const [dataErr, setDataErr] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  async function loadDashboardData() {
    try {
      const [addonsRes, statsRes, eventsRes, repoRes, schedulerRes, mqttRes] = await Promise.all([
        fetch("/api/addons", { cache: "no-store" }),
        fetch("/api/system/stats/current", { cache: "no-store" }),
        fetch("/api/system/events?limit=8", { cache: "no-store" }),
        fetch("/api/system/repo/status", { cache: "no-store" }),
        fetch("/api/system/scheduler/status", { cache: "no-store" }),
        fetch("/api/system/mqtt/status", { cache: "no-store" }),
      ]);
      if (addonsRes.ok) setAddons((await addonsRes.json()) as AddonSummary[]);
      if (statsRes.ok) setStats((await statsRes.json()) as SystemStats);
      if (eventsRes.ok) {
        const payload = (await eventsRes.json()) as { items?: EventItem[] };
        setEvents(Array.isArray(payload.items) ? payload.items : []);
      }
      if (repoRes.ok) setRepoStatus((await repoRes.json()) as RepoStatus);
      if (schedulerRes.ok) setScheduler((await schedulerRes.json()) as SchedulerStatus);
      if (mqttRes.ok) setMqtt((await mqttRes.json()) as MqttStatus);
      setDataErr(null);
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (e: unknown) {
      setDataErr(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void loadDashboardData();
    const id = setInterval(() => {
      void loadDashboardData();
    }, 10000);
    return () => clearInterval(id);
  }, []);

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

  const installedAddons = useMemo(
    () => addons.filter((item) => item.enabled !== false).sort((a, b) => a.id.localeCompare(b.id)),
    [addons],
  );

  const unhealthyAddons = useMemo(
    () => installedAddons.filter((item) => String(item.health_status || "").toLowerCase() === "unhealthy").length,
    [installedAddons],
  );

  const coreRunning = true;
  const supervisorRunning = !!stats?.services?.supervisor?.running;
  const mqttConnected = !!mqtt?.connected;
  const activeWorkers = scheduler?.snapshot?.active_leases ?? 0;
  const queueDepth = Object.values(scheduler?.snapshot?.queue_depths || {}).reduce((acc, x) => acc + x, 0);

  const statusState = useMemo(() => {
    if (!stats) return { label: "OFFLINE", detail: "System stats unavailable", tone: "danger" };
    if (!supervisorRunning) return { label: "ATTENTION", detail: "Supervisor not running", tone: "danger" };
    if (!mqttConnected || unhealthyAddons > 0) return { label: "DEGRADED", detail: "Some subsystems need attention", tone: "warn" };
    return { label: "READY", detail: "Core services healthy", tone: "ok" };
  }, [stats, supervisorRunning, mqttConnected, unhealthyAddons]);

  return (
    <div className="home-page">
      <section className="home-head">
        <div>
          <h1 className="home-title">Home Dashboard</h1>
          <p className="home-subtitle">
            Operational overview for core services, addons, workers, and recent platform activity.
          </p>
        </div>
        <div className="home-head-meta">
          <span className="home-pill">{repoStatus?.update_available ? "Update available" : "Core up to date"}</span>
          <span className="home-pill home-pill-muted">
            {stats ? `${stats.hostname} • uptime ${fmtUptime(stats.uptime_s)}` : "Host unavailable"}
          </span>
          {lastUpdated && <span className="home-pill home-pill-muted">updated {lastUpdated}</span>}
        </div>
      </section>

      <section className={`home-status-card tone-${statusState.tone}`}>
        <div>
          <div className="home-status-label">{statusState.label}</div>
          <div className="home-status-detail">{statusState.detail}</div>
        </div>
        <div className="home-subsystems">
          <span className={`home-subsystem ${coreRunning ? "ok" : "bad"}`}>Core</span>
          <span className={`home-subsystem ${supervisorRunning ? "ok" : "bad"}`}>Supervisor</span>
          <span className={`home-subsystem ${mqttConnected ? "ok" : "warn"}`}>MQTT</span>
          <span className={`home-subsystem ${activeWorkers > 0 ? "ok" : "neutral"}`}>Workers</span>
          <span className={`home-subsystem ${unhealthyAddons === 0 ? "ok" : "warn"}`}>Addons</span>
        </div>
      </section>

      <section className="home-status-row">
        <StatusMini title="Core" value={coreRunning ? "online" : "offline"} />
        <StatusMini title="Supervisor" value={supervisorRunning ? "running" : "down"} />
        <StatusMini title="Addons" value={`${installedAddons.length}`} />
        <StatusMini title="Workers" value={`${activeWorkers}`} sub={queueDepth > 0 ? `${queueDepth} queued` : "idle"} />
        <StatusMini title="Busy" value={stats ? `${stats.busy_rating.toFixed(1)}/10` : "—"} />
      </section>

      <section className="home-session-strip">
        {!ready ? (
          <div className="home-session-card">Checking session...</div>
        ) : authenticated ? (
          <div className="home-session-card">
            <span>Admin session active</span>
            <button className="home-btn" onClick={submitLogout} disabled={busy}>
              {busy ? "Signing out..." : "Sign out"}
            </button>
          </div>
        ) : (
          <div className="home-session-card home-session-login">
            <span>Guest mode active</span>
            <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="admin" className="home-input" />
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              type="password"
              className="home-input"
            />
            <button className="home-btn" onClick={submitLogin} disabled={busy || !username.trim() || !password}>
              {busy ? "Signing in..." : "Sign in"}
            </button>
          </div>
        )}
        {err && <div className="home-auth-err">{err}</div>}
      </section>

      {dataErr && <div className="home-data-err">Dashboard data load failed: {dataErr}</div>}

      <section className="home-grid">
        <article className="home-panel">
          <div className="home-panel-head">
            <h2>Installed Addons</h2>
            <Link to="/addons" className="home-link">Open Addons</Link>
          </div>
          {installedAddons.length === 0 ? (
            <div className="home-empty">No installed addons yet.</div>
          ) : (
            <div className="home-addon-list">
              {installedAddons.slice(0, 10).map((item) => (
                <div key={item.id} className="home-addon-item">
                  <div>
                    <div className="home-addon-name">{item.name || item.id}</div>
                    <div className="home-addon-meta">{item.id} • {item.version || "unknown"}</div>
                  </div>
                  <span className={`home-chip state-${String(item.health_status || "unknown").toLowerCase()}`}>
                    {item.health_status || "unknown"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="home-panel">
          <div className="home-panel-head">
            <h2>Recent Activity</h2>
          </div>
          {events.length === 0 ? (
            <div className="home-empty">No recent event entries available.</div>
          ) : (
            <div className="home-activity-list">
              {events.map((item) => (
                <div key={item.id} className="home-activity-item">
                  <div className="home-activity-top">
                    <span className="home-chip">{item.event_type}</span>
                    <span className="home-activity-time">{relative(item.timestamp)}</span>
                  </div>
                  <div className="home-activity-source">{item.source}</div>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="home-panel">
          <div className="home-panel-head">
            <h2>System Metrics</h2>
          </div>
          {!stats ? (
            <div className="home-empty">Metrics unavailable.</div>
          ) : (
            <div className="home-metrics">
              <MetricRow label="CPU" value={pct(stats.cpu.percent_total)} />
              <MetricRow label="Memory" value={pct(stats.mem.percent)} />
              <MetricRow
                label="Disk"
                value={pct(
                  Object.values(stats.disks).length > 0
                    ? Math.max(...Object.values(stats.disks).map((x) => x.percent))
                    : 0,
                )}
              />
            </div>
          )}
        </article>
      </section>
    </div>
  );
}

function StatusMini({ title, value, sub }: { title: string; value: string; sub?: string }) {
  return (
    <div className="home-mini">
      <div className="home-mini-title">{title}</div>
      <div className="home-mini-value">{value}</div>
      {sub && <div className="home-mini-sub">{sub}</div>}
    </div>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="home-metric-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
