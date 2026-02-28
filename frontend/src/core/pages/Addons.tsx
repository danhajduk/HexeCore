import { useEffect, useState } from "react";
import { apiGet } from "../api/client";
import "./addons.css";

type AddonInfo = {
  id: string;
  name: string;
  version: string;
  description: string;
  show_sidebar?: boolean;
  enabled?: boolean;
  base_url?: string | null;
  capabilities?: string[];
  health_status?: string;
  last_seen?: string | null;
  auth_mode?: string;
  tls_warning?: string | null;
  discovery_source?: string;
};

export default function Addons() {
  const [addons, setAddons] = useState<AddonInfo[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    apiGet<AddonInfo[]>("/api/addons")
      .then(setAddons)
      .catch((e) => setErr(String(e)));
  }, []);

  async function setEnabled(addonId: string, enabled: boolean) {
    setErr(null);
    setBusy(addonId);
    try {
      const res = await fetch(`/api/addons/${addonId}/enable`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAddons((prev) =>
        prev.map((a) => (a.id === addonId ? { ...a, enabled: data.enabled } : a))
      );
    } catch (e: any) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <h1 className="addons-title">Addons</h1>
      {err && <pre className="addons-error">{err}</pre>}
      {!err && (
        <div className="addons-container">
          <div className="addons-list">
          {addons.length === 0 ? (
            <div className="addons-empty">No backend addons loaded.</div>
          ) : (
            addons.map((a) => (
              <div
                key={a.id}
                className="addon-card"
              >
                <div className="addon-card-header">
                  <div className="addon-name">{a.name}</div>
                  <div className="addon-status">
                    {a.enabled === false ? "disabled" : "enabled"}
                  </div>
                </div>
                <div className="addon-meta">{a.id} • {a.version}</div>
                {a.base_url && <div className="addon-meta">base_url: {a.base_url}</div>}
                <div className="addon-meta">
                  health: {a.health_status ?? "unknown"}
                  {a.auth_mode ? ` • auth: ${a.auth_mode}` : ""}
                  {a.discovery_source ? ` • source: ${a.discovery_source}` : ""}
                </div>
                {a.last_seen && (
                  <div className="addon-meta">last seen: {new Date(a.last_seen).toLocaleString()}</div>
                )}
                {a.capabilities && a.capabilities.length > 0 && (
                  <div className="addon-desc">capabilities: {a.capabilities.join(", ")}</div>
                )}
                {a.tls_warning && <div className="addons-error">{a.tls_warning}</div>}
                {a.description && <div className="addon-desc">{a.description}</div>}
                <div className="addon-actions">
                  <button
                    onClick={() => setEnabled(a.id, !(a.enabled ?? true))}
                    disabled={busy === a.id}
                    className="addon-btn"
                  >
                    {a.enabled === false ? "Enable" : "Disable"}
                  </button>
                  <a
                    href={`/addons/${a.id}`}
                    className="addon-btn"
                  >
                    Open
                  </a>
                </div>
              </div>
            ))
          )}
          </div>
        </div>
      )}
    </div>
  );
}
