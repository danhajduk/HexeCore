import { useEffect, useState } from "react";
import { usePlatformBranding } from "../branding";
import "./settings.css";

type EdgeIdentity = {
  core_id: string;
  core_name: string;
  platform_domain: string;
  public_ui_hostname: string;
  public_api_hostname: string;
};

type CloudflareSettings = {
  enabled: boolean;
  account_id?: string | null;
  zone_id?: string | null;
  tunnel_id?: string | null;
  tunnel_name?: string | null;
  credentials_reference?: string | null;
  managed_domain_base: string;
  hostname_publication_mode: string;
};

type EdgePublication = {
  publication_id: string;
  hostname: string;
  path_prefix: string;
  enabled: boolean;
  source: string;
  target: {
    target_type: string;
    target_id: string;
    upstream_base_url: string;
  };
};

type EdgeStatus = {
  public_identity: EdgeIdentity;
  cloudflare: CloudflareSettings;
  tunnel: {
    configured: boolean;
    runtime_state: string;
    healthy: boolean;
    config_path?: string | null;
    last_error?: string | null;
  };
  publications: EdgePublication[];
  reconcile_state: Record<string, unknown>;
  validation_errors: string[];
};

const EMPTY_SETTINGS: CloudflareSettings = {
  enabled: false,
  account_id: "",
  zone_id: "",
  tunnel_id: "",
  tunnel_name: "",
  credentials_reference: "",
  managed_domain_base: "hexe-ai.com",
  hostname_publication_mode: "core_id_managed",
};

export default function EdgeGateway() {
  const branding = usePlatformBranding();
  const [status, setStatus] = useState<EdgeStatus | null>(null);
  const [settings, setSettings] = useState<CloudflareSettings>(EMPTY_SETTINGS);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [publicationForm, setPublicationForm] = useState({
    hostname: "",
    path_prefix: "/",
    target_type: "local_service",
    target_id: "",
    upstream_base_url: "http://127.0.0.1:8081",
  });

  async function load() {
    setErr(null);
    try {
      const [statusRes, settingsRes] = await Promise.all([
        fetch("/api/edge/status", { cache: "no-store" }),
        fetch("/api/edge/cloudflare/settings", { cache: "no-store" }),
      ]);
      if (!statusRes.ok) throw new Error(`status HTTP ${statusRes.status}`);
      if (!settingsRes.ok) throw new Error(`settings HTTP ${settingsRes.status}`);
      const statusPayload = (await statusRes.json()) as EdgeStatus;
      const settingsPayload = (await settingsRes.json()) as CloudflareSettings;
      setStatus(statusPayload);
      setSettings({ ...EMPTY_SETTINGS, ...settingsPayload });
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    }
  }

  async function saveSettings() {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/edge/cloudflare/settings", {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      if (!res.ok) throw new Error(`save HTTP ${res.status}`);
      await load();
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runAction(path: string) {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(path, { method: "POST", credentials: "include" });
      if (!res.ok) throw new Error(`action HTTP ${res.status}`);
      await load();
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  async function createPublication() {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/edge/publications", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hostname: publicationForm.hostname,
          path_prefix: publicationForm.path_prefix,
          enabled: true,
          source: "operator_defined",
          target: {
            target_type: publicationForm.target_type,
            target_id: publicationForm.target_id,
            upstream_base_url: publicationForm.upstream_base_url,
            allowed_path_prefixes: [publicationForm.path_prefix],
          },
        }),
      });
      if (!res.ok) throw new Error(`create HTTP ${res.status}`);
      setPublicationForm({
        hostname: "",
        path_prefix: "/",
        target_type: "local_service",
        target_id: "",
        upstream_base_url: "http://127.0.0.1:8081",
      });
      await load();
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  async function togglePublication(item: EdgePublication) {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`/api/edge/publications/${encodeURIComponent(item.publication_id)}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !item.enabled }),
      });
      if (!res.ok) throw new Error(`patch HTTP ${res.status}`);
      await load();
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  async function deletePublication(publicationId: string) {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`/api/edge/publications/${encodeURIComponent(publicationId)}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!res.ok) throw new Error(`delete HTTP ${res.status}`);
      await load();
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="settings-page">
      <h1 className="settings-title">Edge Gateway</h1>
      <p className="settings-page-subtitle">
        Public ingress for {branding.coreName} using platform-managed Cloudflare hostnames in V1 single-owner mode.
      </p>
      {err && <div className="settings-error">Edge Gateway error: {err}</div>}

      <section className="settings-section">
        <div className="settings-section-head">
          <h2>Public Identity</h2>
          <p>Stable Core identity and derived public hostnames.</p>
        </div>
        <div className="settings-card">
          <div className="settings-kv-grid">
            <div className="settings-kv-item">
              <div className="settings-label-text">Core ID</div>
              <div className="settings-mono">{status?.public_identity.core_id || "loading"}</div>
            </div>
            <div className="settings-kv-item">
              <div className="settings-label-text">UI hostname</div>
              <div className="settings-mono">{status?.public_identity.public_ui_hostname || "loading"}</div>
            </div>
            <div className="settings-kv-item">
              <div className="settings-label-text">API hostname</div>
              <div className="settings-mono">{status?.public_identity.public_api_hostname || "loading"}</div>
            </div>
            <div className="settings-kv-item">
              <div className="settings-label-text">Managed domain</div>
              <div className="settings-mono">{status?.public_identity.platform_domain || "hexe-ai.com"}</div>
            </div>
          </div>
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <h2>Cloudflare</h2>
          <p>Platform-managed Cloudflare configuration for the shared Hexe AI domain.</p>
        </div>
        <div className="settings-card">
          <div className="settings-form">
            <label className="settings-toggle">
              <input
                type="checkbox"
                checked={settings.enabled}
                onChange={(e) => setSettings((current) => ({ ...current, enabled: e.target.checked }))}
              />
              <span>Enable Cloudflare publication</span>
            </label>
            {["account_id", "zone_id", "tunnel_id", "tunnel_name", "credentials_reference"].map((field) => (
              <label key={field} className="settings-label">
                <div className="settings-label-text">{field.replace(/_/g, " ")}</div>
                <input
                  value={String((settings as Record<string, unknown>)[field] || "")}
                  onChange={(e) => setSettings((current) => ({ ...current, [field]: e.target.value }))}
                  className="settings-input"
                />
              </label>
            ))}
            <label className="settings-label">
              <div className="settings-label-text">Managed domain base</div>
              <input
                value={settings.managed_domain_base}
                onChange={(e) => setSettings((current) => ({ ...current, managed_domain_base: e.target.value }))}
                className="settings-input"
              />
            </label>
            <div className="settings-row-actions">
              <button className="settings-btn" disabled={busy} onClick={saveSettings}>
                {busy ? "Saving..." : "Save Cloudflare settings"}
              </button>
              <button className="settings-btn secondary" disabled={busy} onClick={() => void runAction("/api/edge/cloudflare/test")}>
                Dry-run test
              </button>
              <button className="settings-btn secondary" disabled={busy} onClick={() => void runAction("/api/edge/reconcile")}>
                Reconcile
              </button>
            </div>
          </div>
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <h2>Status</h2>
          <p>Current publication and tunnel state.</p>
        </div>
        <div className="settings-card">
          <div className="settings-kv-grid">
            <div className="settings-kv-item">
              <div className="settings-label-text">Tunnel state</div>
              <span className="settings-pill">{status?.tunnel.runtime_state || "unknown"}</span>
            </div>
            <div className="settings-kv-item">
              <div className="settings-label-text">Configured</div>
              <span className="settings-pill">{status?.tunnel.configured ? "Configured" : "Not configured"}</span>
            </div>
            <div className="settings-kv-item">
              <div className="settings-label-text">Validation errors</div>
              <div>{status?.validation_errors.length ? status.validation_errors.join(", ") : "None"}</div>
            </div>
            <div className="settings-kv-item">
              <div className="settings-label-text">Config path</div>
              <div className="settings-mono">{status?.tunnel.config_path || "Not written yet"}</div>
            </div>
          </div>
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <h2>Publications</h2>
          <p>Core-owned hostnames are derived automatically; extra publications remain platform-owned in V1.</p>
        </div>
        <div className="settings-card">
          <div className="settings-form">
            <label className="settings-label">
              <div className="settings-label-text">Hostname</div>
              <input
                value={publicationForm.hostname}
                onChange={(e) => setPublicationForm((current) => ({ ...current, hostname: e.target.value }))}
                className="settings-input"
                placeholder={`service.${status?.public_identity.core_id || "coreid"}.hexe-ai.com`}
              />
            </label>
            <label className="settings-label">
              <div className="settings-label-text">Path prefix</div>
              <input
                value={publicationForm.path_prefix}
                onChange={(e) => setPublicationForm((current) => ({ ...current, path_prefix: e.target.value }))}
                className="settings-input"
              />
            </label>
            <label className="settings-label">
              <div className="settings-label-text">Target type</div>
              <select
                value={publicationForm.target_type}
                onChange={(e) => setPublicationForm((current) => ({ ...current, target_type: e.target.value }))}
                className="settings-select-input"
              >
                <option value="local_service">Local service</option>
                <option value="supervisor_runtime">Supervisor runtime</option>
                <option value="node">Node</option>
              </select>
            </label>
            <label className="settings-label">
              <div className="settings-label-text">Target id</div>
              <input
                value={publicationForm.target_id}
                onChange={(e) => setPublicationForm((current) => ({ ...current, target_id: e.target.value }))}
                className="settings-input"
              />
            </label>
            <label className="settings-label">
              <div className="settings-label-text">Upstream base URL</div>
              <input
                value={publicationForm.upstream_base_url}
                onChange={(e) => setPublicationForm((current) => ({ ...current, upstream_base_url: e.target.value }))}
                className="settings-input"
              />
            </label>
            <div className="settings-row-actions">
              <button className="settings-btn" disabled={busy} onClick={createPublication}>
                {busy ? "Working..." : "Create publication"}
              </button>
            </div>
          </div>
        </div>
        <div className="settings-card">
          <div className="settings-kv-grid">
            {(status?.publications || []).map((item) => (
              <div key={item.publication_id} className="settings-kv-item">
                <div className="settings-label-text">{item.publication_id}</div>
                <div className="settings-mono">{item.hostname}{item.path_prefix}</div>
                <div>{item.target.target_type} {"->"} {item.target.upstream_base_url}</div>
                <div className="settings-row-actions">
                  <button className="settings-btn secondary" disabled={busy || item.source === "core_owned"} onClick={() => void togglePublication(item)}>
                    {item.enabled ? "Disable" : "Enable"}
                  </button>
                  <button className="settings-btn secondary" disabled={busy || item.source === "core_owned"} onClick={() => void deletePublication(item.publication_id)}>
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
