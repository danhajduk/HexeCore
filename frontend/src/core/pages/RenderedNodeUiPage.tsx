import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import {
  executeNodeUiAction,
  NodeUiCard,
  useNodeSurfaceData,
  useNodeUiManifest,
  type NodeUiAction,
  type NodeUiActionState,
  type NodeUiCardResponse,
  type NodeUiManifest,
  type NodeUiPage,
  type NodeUiSurface,
} from "../rendered-node-ui";
import "./rendered-node-ui-page.css";

export function resolveSelectedNodeUiPage(manifest: NodeUiManifest, selectedPageId?: string | null): NodeUiPage {
  const pages = manifest.pages || [];
  return pages.find((page) => page.id === selectedPageId) || pages[0];
}

export function nodeUiSurfacePollInterval(surface: NodeUiSurface): number | null {
  const mode = surface.refresh?.mode;
  if (mode !== "live" && mode !== "near_live") return null;
  const interval = Number(surface.refresh?.interval_ms || 0);
  return Number.isFinite(interval) && interval > 0 ? interval : null;
}

export function resolveNodeUiAction(surface: NodeUiSurface, actionState: NodeUiActionState): NodeUiAction | null {
  return (surface.actions || []).find((action) => action.id === actionState.id) || null;
}

export function nodeUiActionConfirmationMessage(action: NodeUiAction): string | null {
  const confirmation = action.confirmation;
  if (!confirmation?.required) return null;
  return confirmation.message || confirmation.title || `Run ${action.label}?`;
}

function SurfaceCard({ nodeId, surface }: { nodeId: string; surface: NodeUiSurface }) {
  const data = useNodeSurfaceData<NodeUiCardResponse>(nodeId, surface.data_endpoint);
  const pollInterval = nodeUiSurfacePollInterval(surface);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!pollInterval) return;
    const timer = window.setInterval(() => data.reload(), pollInterval);
    return () => window.clearInterval(timer);
  }, [data.reload, pollInterval]);

  async function handleAction(actionState: NodeUiActionState) {
    const action = resolveNodeUiAction(surface, actionState);
    setActionMessage(null);
    setActionError(null);
    if (!action) {
      setActionError("Action is not declared in the manifest.");
      return;
    }
    const confirmation = nodeUiActionConfirmationMessage(action);
    if (confirmation && !window.confirm(confirmation)) return;
    try {
      await executeNodeUiAction(nodeId, action);
      setActionMessage(`${action.label} complete.`);
      data.reload();
    } catch (error: unknown) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  }

  if (data.status === "loading" && !data.data) {
    return (
      <article className="rendered-node-surface-state">
        <h3>{surface.title}</h3>
        <p>Loading...</p>
      </article>
    );
  }

  if (data.status === "error" || !data.data) {
    return (
      <article className="rendered-node-surface-state rendered-node-surface-error">
        <div>
          <h3>{surface.title}</h3>
          <p>{data.error || "Surface data unavailable."}</p>
        </div>
        <button type="button" className="rendered-node-refresh" onClick={data.reload} title="Refresh">
          <RefreshCw size={16} aria-hidden="true" />
        </button>
      </article>
    );
  }

  return (
    <div className="rendered-node-surface-wrap">
      <NodeUiCard surface={surface} data={data.data} onAction={(action) => void handleAction(action)} />
      {actionMessage ? <div className="rendered-node-action-status tone-success">{actionMessage}</div> : null}
      {actionError ? <div className="rendered-node-action-status tone-error">{actionError}</div> : null}
      <button type="button" className="rendered-node-refresh rendered-node-refresh-overlay" onClick={data.reload} title="Refresh">
        <RefreshCw size={16} aria-hidden="true" />
      </button>
    </div>
  );
}

function LegacyNodeUiFallback({ nodeId }: { nodeId: string }) {
  return (
    <Link to={`/nodes/${encodeURIComponent(nodeId)}/UI`} className="rendered-node-fallback-link">
      Open legacy UI
    </Link>
  );
}

export default function RenderedNodeUiPage() {
  const { nodeId = "" } = useParams();
  const manifestState = useNodeUiManifest(nodeId);
  const manifest = manifestState.data?.manifest || null;
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);

  useEffect(() => {
    setSelectedPageId(null);
  }, [nodeId, manifestState.data?.manifest_revision]);

  const activePage = useMemo(
    () => (manifest ? resolveSelectedNodeUiPage(manifest, selectedPageId) : null),
    [manifest, selectedPageId],
  );

  return (
    <section className="rendered-node-page">
      <header className="rendered-node-page-head">
        <div className="rendered-node-page-title">
          <Link to={`/nodes/${encodeURIComponent(nodeId)}`} className="rendered-node-back">
            <ArrowLeft size={16} aria-hidden="true" />
            <span>Node details</span>
          </Link>
          <div className="rendered-node-eyebrow">Core-rendered node UI</div>
          <h1>{manifest?.display_name || nodeId}</h1>
          {manifest ? (
            <p>
              {manifest.node_type}
              {manifest.manifest_revision ? ` · ${manifest.manifest_revision}` : ""}
            </p>
          ) : null}
        </div>
        <button type="button" className="rendered-node-refresh" onClick={manifestState.reload} title="Refresh manifest">
          <RefreshCw size={16} aria-hidden="true" />
        </button>
      </header>

      {manifestState.status === "loading" && !manifestState.data ? (
        <div className="rendered-node-shell-state">Loading manifest...</div>
      ) : manifestState.status === "error" ? (
        <div className="rendered-node-shell-state rendered-node-shell-error">
          <span>{manifestState.error}</span>
          <LegacyNodeUiFallback nodeId={nodeId} />
        </div>
      ) : manifestState.data && !manifestState.data.ok ? (
        <div className="rendered-node-shell-state rendered-node-shell-error">
          <strong>{manifestState.data.status}</strong>
          <span>{manifestState.data.detail || manifestState.data.error_code}</span>
          <LegacyNodeUiFallback nodeId={nodeId} />
        </div>
      ) : manifest && activePage ? (
        <>
          <nav className="rendered-node-tabs" aria-label="Node UI pages">
            {manifest.pages.map((page) => (
              <button
                key={page.id}
                type="button"
                className={page.id === activePage.id ? "is-active" : ""}
                onClick={() => setSelectedPageId(page.id)}
              >
                {page.title}
              </button>
            ))}
          </nav>

          <section className="rendered-node-page-section">
            <div className="rendered-node-section-head">
              <div>
                <h2>{activePage.title}</h2>
                {activePage.description ? <p>{activePage.description}</p> : null}
              </div>
            </div>
            <div className="rendered-node-surface-grid">
              {activePage.surfaces.map((surface) => (
                <SurfaceCard key={surface.id} nodeId={nodeId} surface={surface} />
              ))}
            </div>
          </section>
        </>
      ) : (
        <div className="rendered-node-shell-state rendered-node-shell-error">Manifest has no pages.</div>
      )}
    </section>
  );
}
