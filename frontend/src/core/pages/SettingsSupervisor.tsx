import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import "./settings.css";

type SupervisorHostResources = {
  uptime_s?: number;
  load_1m?: number;
  load_5m?: number;
  load_15m?: number;
  cpu_percent_total?: number;
  cpu_cores_logical?: number;
  memory_total_bytes?: number;
  memory_available_bytes?: number;
  memory_percent?: number;
  root_disk_total_bytes?: number | null;
  root_disk_free_bytes?: number | null;
  root_disk_percent?: number | null;
};

type SupervisorHostProcess = {
  rss_bytes?: number | null;
  cpu_percent?: number | null;
  open_fds?: number | null;
  threads?: number | null;
};

type SupervisorRuntimeSummary = {
  host?: { host_id?: string; hostname?: string };
  resources?: SupervisorHostResources;
  process?: SupervisorHostProcess;
  managed_nodes?: Array<Record<string, unknown>>;
};

type SupervisorHealthSummary = {
  status?: string;
  host?: { host_id?: string; hostname?: string };
  resources?: SupervisorHostResources;
  managed_node_count?: number;
  healthy_node_count?: number;
  unhealthy_node_count?: number;
};

type SupervisorSummary = {
  ok: boolean;
  available?: boolean;
  error?: string;
  health?: SupervisorHealthSummary | null;
  runtime?: SupervisorRuntimeSummary | null;
  info?: Record<string, unknown> | null;
  nodes?: Array<Record<string, unknown>>;
  runtimes?: Array<Record<string, unknown>>;
  core_runtimes?: Array<Record<string, unknown>>;
};

function displayState(value: unknown): string {
  const raw = String(value || "unknown").trim();
  if (!raw) return "Unknown";
  const normalized = raw.replace(/_/g, " ").toLowerCase();
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function formatNumber(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "number" && Number.isFinite(value)) return value.toLocaleString();
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toLocaleString() : fallback;
}

function formatBytes(value: unknown): string {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = parsed;
  let idx = 0;
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024;
    idx += 1;
  }
  return `${size.toFixed(size >= 100 ? 0 : 1)} ${units[idx]}`;
}

function renderMetadata(meta?: Record<string, unknown>): JSX.Element | null {
  if (!meta || Object.keys(meta).length === 0) return null;
  return <pre className="settings-pre">{JSON.stringify(meta, null, 2)}</pre>;
}

export default function SettingsSupervisor() {
  const [summary, setSummary] = useState<SupervisorSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadSummary() {
    setErr(null);
    setLoading(true);
    try {
      const res = await fetch("/api/system/supervisor/summary", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSummary((await res.json()) as SupervisorSummary);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSummary();
  }, []);

  const resources = summary?.health?.resources || summary?.runtime?.resources || {};
  const process = summary?.runtime?.process || {};
  const coreRuntimes = Array.isArray(summary?.core_runtimes) ? summary?.core_runtimes : [];
  const nodeRuntimes = Array.isArray(summary?.runtimes) ? summary?.runtimes : [];
  const managedNodes = Array.isArray(summary?.nodes) ? summary?.nodes : [];

  return (
    <div className="settings-page">
      <h1 className="settings-title">Settings / Supervisor</h1>
      <p className="settings-muted">
        Local Supervisor telemetry, host metrics, and registered runtime inventory for Core services, addons, aux containers, and
        node runtimes.
      </p>
      <div className="settings-row">
        <div />
        <div className="settings-row-actions">
          <Link className="settings-btn" to="/settings">
            Back to settings
          </Link>
          <button className="settings-btn" onClick={() => void loadSummary()} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh supervisor data"}
          </button>
        </div>
      </div>

      {err && <div className="settings-error">Failed to load supervisor summary: {err}</div>}
      {summary?.error && <div className="settings-error">Supervisor error: {summary.error}</div>}

      <section className="settings-section">
        <div className="settings-section-head">
          <h2>Host Metrics</h2>
          <p>Supervisor-owned host telemetry and process stats.</p>
        </div>
        <div className="settings-card">
          <div className="settings-kv-grid">
            <div className="settings-kv-item">
              <div className="settings-label-text">Supervisor status</div>
              <span className="settings-pill">{displayState(summary?.health?.status)}</span>
            </div>
            <div className="settings-kv-item">
              <div className="settings-label-text">Host</div>
              <div className="settings-mono">{summary?.health?.host?.hostname || "-"}</div>
              <div className="settings-help">ID {summary?.health?.host?.host_id || "-"}</div>
            </div>
            <div className="settings-kv-item">
              <div className="settings-label-text">Uptime</div>
              <div>{formatNumber(resources.uptime_s)}s</div>
              <div className="settings-help">Load {formatNumber(resources.load_1m)} / {formatNumber(resources.load_5m)} / {formatNumber(resources.load_15m)}</div>
            </div>
            <div className="settings-kv-item">
              <div className="settings-label-text">CPU</div>
              <div>{formatNumber(resources.cpu_percent_total)}% used</div>
              <div className="settings-help">Logical cores {formatNumber(resources.cpu_cores_logical)}</div>
            </div>
            <div className="settings-kv-item">
              <div className="settings-label-text">Memory</div>
              <div>{formatNumber(resources.memory_percent)}% used</div>
              <div className="settings-help">
                {formatBytes(resources.memory_available_bytes)} available / {formatBytes(resources.memory_total_bytes)}
              </div>
            </div>
            <div className="settings-kv-item">
              <div className="settings-label-text">Root disk</div>
              <div>{formatNumber(resources.root_disk_percent)}% used</div>
              <div className="settings-help">
                {formatBytes(resources.root_disk_free_bytes)} free / {formatBytes(resources.root_disk_total_bytes)}
              </div>
            </div>
            <div className="settings-kv-item">
              <div className="settings-label-text">Supervisor process</div>
              <div>{formatBytes(process.rss_bytes)} RSS</div>
              <div className="settings-help">CPU {formatNumber(process.cpu_percent)}% • Threads {formatNumber(process.threads)}</div>
            </div>
          </div>
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <h2>Core Services & Aux Runtimes</h2>
          <p>Core-owned services, addons, and aux containers registered with the local Supervisor.</p>
        </div>
        <div className="settings-card">
          {coreRuntimes.length === 0 && <div className="settings-help">No Core runtimes registered yet.</div>}
          {coreRuntimes.map((runtime) => (
            <div key={String(runtime.runtime_id || runtime.runtime_name)} className="settings-kv-item">
              <div className="settings-label-text">{String(runtime.runtime_name || runtime.runtime_id || "Unnamed")}</div>
              <div className="settings-help">ID {String(runtime.runtime_id || "-")}</div>
              <div className="settings-help">Kind {displayState(runtime.runtime_kind)} • Mode {displayState(runtime.management_mode)}</div>
              <div className="settings-help">
                State {displayState(runtime.runtime_state)} • Health {displayState(runtime.health_status)} • Desired {displayState(runtime.desired_state)}
              </div>
              {renderMetadata(runtime.runtime_metadata as Record<string, unknown>)}
            </div>
          ))}
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <h2>Node Runtimes</h2>
          <p>Supervisor-registered Node runtime inventory and aux metadata.</p>
        </div>
        <div className="settings-card">
          {nodeRuntimes.length === 0 && <div className="settings-help">No node runtimes registered yet.</div>}
          {nodeRuntimes.map((runtime) => (
            <div key={String(runtime.node_id || runtime.node_name)} className="settings-kv-item">
              <div className="settings-label-text">{String(runtime.node_name || runtime.node_id || "Unnamed")}</div>
              <div className="settings-help">ID {String(runtime.node_id || "-")} • Type {String(runtime.node_type || "-")}</div>
              <div className="settings-help">
                State {displayState(runtime.runtime_state)} • Health {displayState(runtime.health_status)} • Desired {displayState(runtime.desired_state)}
              </div>
              {renderMetadata(runtime.runtime_metadata as Record<string, unknown>)}
            </div>
          ))}
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <h2>Standalone Addon Runtimes</h2>
          <p>Supervisor-managed standalone addon lifecycle state (compatibility view).</p>
        </div>
        <div className="settings-card">
          {managedNodes.length === 0 && <div className="settings-help">No standalone addon runtimes listed.</div>}
          {managedNodes.map((node) => (
            <div key={String(node.node_id || node.node_name)} className="settings-kv-item">
              <div className="settings-label-text">{String(node.node_id || node.node_name || "Addon")}</div>
              <div className="settings-help">State {displayState(node.runtime_state)} • Health {displayState(node.health_status)}</div>
              {renderMetadata(node as Record<string, unknown>)}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
