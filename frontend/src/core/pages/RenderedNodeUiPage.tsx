import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Layers3, RefreshCw, ServerCog } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import {
  executeNodeUiAction,
  NodeUiCard,
  useNodePageData,
  useNodeSurfaceData,
  useNodeUiManifest,
  type NodeUiAction,
  type NodeUiActionState,
  type NodeUiCardResponse,
  type NodeUiManifest,
  type NodeUiPage,
  type NodeUiPageCard,
  type NodeUiRefreshPolicy,
  type NodeUiSurface,
} from "../rendered-node-ui";
import "./rendered-node-ui-page.css";

export function resolveSelectedNodeUiPage(manifest: NodeUiManifest, selectedPageId?: string | null): NodeUiPage {
  const pages = manifest.pages || [];
  return pages.find((page) => page.id === selectedPageId) || pages[0];
}

export function nodeUiSurfacePollInterval(surface: NodeUiSurface): number | null {
  return nodeUiRefreshPollInterval(surface.refresh);
}

export function nodeUiRefreshPollInterval(refresh?: NodeUiRefreshPolicy | null): number | null {
  const mode = refresh?.mode;
  if (mode !== "live" && mode !== "near_live") return null;
  const interval = Number(refresh?.interval_ms || 0);
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

export function resolveNodeUiPageSurfaces(page: NodeUiPage): NodeUiSurface[] {
  return page.surfaces.filter((surface) => surface.kind !== "node_overview").sort((left, right) => {
    if (left.kind === right.kind) return 0;
    if (left.kind === "health_strip") return -1;
    if (right.kind === "health_strip") return 1;
    return 0;
  });
}

export function resolveNodeUiPageCards(cards: NodeUiPageCard[]): NodeUiPageCard[] {
  return cards.filter((card) => card.kind !== "node_overview").sort((left, right) => {
    if (left.kind === right.kind) return 0;
    if (left.kind === "health_strip") return -1;
    if (right.kind === "health_strip") return 1;
    return 0;
  });
}

export function resolveNodeUiManifestDataLabel(manifest: NodeUiManifest): string {
  const pagePayloadCount = manifest.pages.filter((page) => Boolean(page.page_endpoint)).length;
  const surfaceCount = manifest.pages.reduce((total, page) => total + page.surfaces.length, 0);
  const labels: string[] = [];
  if (pagePayloadCount) labels.push(`${pagePayloadCount} page payload${pagePayloadCount === 1 ? "" : "s"}`);
  if (surfaceCount) labels.push(`${surfaceCount} surface${surfaceCount === 1 ? "" : "s"}`);
  return labels.join(" · ") || "No data surfaces";
}

function pageCardToSurface(card: NodeUiPageCard, pageRefresh?: NodeUiRefreshPolicy | null): NodeUiSurface {
  return {
    id: card.id,
    kind: card.kind,
    title: card.title || card.id,
    data_endpoint: "",
    description: card.description,
    detail_endpoint_template: card.detail_endpoint_template,
    actions: card.actions || [],
    refresh: card.refresh || pageRefresh || { mode: "manual" },
  };
}

function surfaceLayoutClass(surface: NodeUiSurface): string {
  return surface.kind === "health_strip" ? " is-health-strip" : "";
}

function loadingClass(isLoading: boolean): string {
  return isLoading ? " is-loading" : "";
}

function RenderedNodeLoadingOverlay({ label = "Loading" }: { label?: string }) {
  return (
    <div className="rendered-node-loading-overlay" role="status" aria-live="polite">
      <div className="rendered-node-loading-spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
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
      <article className={`rendered-node-surface-state rendered-node-loading-shell${surfaceLayoutClass(surface)}`}>
        <div className="rendered-node-loading-backdrop" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <RenderedNodeLoadingOverlay label={surface.title} />
      </article>
    );
  }

  if (data.status === "error" || !data.data) {
    return (
      <article className={`rendered-node-surface-state rendered-node-surface-error${surfaceLayoutClass(surface)}`}>
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
    <div className={`rendered-node-surface-wrap${surfaceLayoutClass(surface)}${loadingClass(data.status === "loading")}`}>
      <div className="rendered-node-loading-content">
        <NodeUiCard surface={surface} data={data.data} onAction={(action) => void handleAction(action)} />
        {actionMessage ? <div className="rendered-node-action-status tone-success">{actionMessage}</div> : null}
        {actionError ? <div className="rendered-node-action-status tone-error">{actionError}</div> : null}
      </div>
      {data.status === "loading" ? <RenderedNodeLoadingOverlay label={`Refreshing ${surface.title}`} /> : null}
      <button
        type="button"
        className={`rendered-node-refresh rendered-node-refresh-overlay${loadingClass(data.status === "loading")}`}
        onClick={data.reload}
        title="Refresh"
        aria-busy={data.status === "loading"}
      >
        <RefreshCw size={16} aria-hidden="true" />
      </button>
    </div>
  );
}

function PageSnapshotCard({
  nodeId,
  card,
  pageRefresh,
  onReload,
}: {
  nodeId: string;
  card: NodeUiPageCard;
  pageRefresh?: NodeUiRefreshPolicy | null;
  onReload: () => void;
}) {
  const surface = pageCardToSurface(card, pageRefresh);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function handleAction(actionState: NodeUiActionState) {
    const action = resolveNodeUiAction(surface, actionState);
    setActionMessage(null);
    setActionError(null);
    if (!action) {
      setActionError("Action is not declared in the page payload.");
      return;
    }
    const confirmation = nodeUiActionConfirmationMessage(action);
    if (confirmation && !window.confirm(confirmation)) return;
    try {
      await executeNodeUiAction(nodeId, action);
      setActionMessage(`${action.label} complete.`);
      onReload();
    } catch (error: unknown) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <div className={`rendered-node-surface-wrap${surfaceLayoutClass(surface)}`}>
      <NodeUiCard surface={surface} data={{ ...card.data, kind: card.data.kind || card.kind }} onAction={(action) => void handleAction(action)} />
      {actionMessage ? <div className="rendered-node-action-status tone-success">{actionMessage}</div> : null}
      {actionError ? <div className="rendered-node-action-status tone-error">{actionError}</div> : null}
    </div>
  );
}

function PageSnapshotSection({ nodeId, page }: { nodeId: string; page: NodeUiPage }) {
  const pageData = useNodePageData(nodeId, page.page_endpoint, { enabled: Boolean(page.page_endpoint) });
  const refresh = pageData.data?.refresh || page.refresh;
  const pollInterval = nodeUiRefreshPollInterval(refresh);

  useEffect(() => {
    if (!pollInterval) return;
    const timer = window.setInterval(() => pageData.reload(), pollInterval);
    return () => window.clearInterval(timer);
  }, [pageData.reload, pollInterval]);

  if (pageData.status === "loading" && !pageData.data) {
    return (
      <section className="rendered-node-page-section">
        <div className="rendered-node-surface-grid">
          <article className="rendered-node-surface-state rendered-node-loading-shell is-health-strip">
            <div className="rendered-node-loading-backdrop" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <RenderedNodeLoadingOverlay label={page.title} />
          </article>
        </div>
      </section>
    );
  }

  if (pageData.status === "error" || !pageData.data) {
    return (
      <section className="rendered-node-page-section">
        <div className="rendered-node-shell-state rendered-node-shell-error">
          <span>{pageData.error || "Page data unavailable."}</span>
          <button type="button" className="rendered-node-refresh" onClick={pageData.reload} title="Refresh page">
            <RefreshCw size={16} aria-hidden="true" />
          </button>
        </div>
      </section>
    );
  }

  const cards = resolveNodeUiPageCards(pageData.data.cards || []);

  return (
    <section className={`rendered-node-page-section rendered-node-content-wrap${loadingClass(pageData.status === "loading")}`}>
      <div className="rendered-node-loading-content">
        <div className="rendered-node-surface-grid">
          {cards.map((card) => (
            <PageSnapshotCard key={card.id} nodeId={nodeId} card={card} pageRefresh={refresh} onReload={pageData.reload} />
          ))}
        </div>
      </div>
      {pageData.status === "loading" ? <RenderedNodeLoadingOverlay label={`Refreshing ${page.title}`} /> : null}
    </section>
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
  const manifestDataLabel = manifest ? resolveNodeUiManifestDataLabel(manifest) : "";

  return (
    <section className="rendered-node-page">
      <header className="rendered-node-page-head">
        <div className="rendered-node-page-title">
          <Link to={`/nodes/${encodeURIComponent(nodeId)}`} className="rendered-node-back">
            <ArrowLeft size={16} aria-hidden="true" />
            <span>Node details</span>
          </Link>
          <div className="rendered-node-title-main">
            <div className="rendered-node-title-icon" aria-hidden="true">
              <ServerCog size={22} />
            </div>
            <div>
              <div className="rendered-node-eyebrow">Core-rendered node UI</div>
              <h1>{manifest?.display_name || nodeId}</h1>
              {manifest ? (
                <p>
                  {manifest.node_type}
                  {manifest.manifest_revision ? ` · ${manifest.manifest_revision}` : ""}
                </p>
              ) : null}
            </div>
          </div>
        </div>
        <div className="rendered-node-page-actions">
          {manifest ? (
            <div className="rendered-node-header-meta" aria-label="Manifest summary">
              <span>{manifest.pages.length} pages</span>
              <span>{manifestDataLabel}</span>
              <span>
                <Layers3 size={14} aria-hidden="true" />
                Schema {manifest.schema_version}
              </span>
            </div>
          ) : null}
          <button
            type="button"
            className={`rendered-node-refresh rendered-node-refresh-wide${loadingClass(manifestState.status === "loading")}`}
            onClick={manifestState.reload}
            title="Refresh manifest"
            aria-busy={manifestState.status === "loading"}
          >
            <span>Refresh</span>
            <RefreshCw size={16} aria-hidden="true" />
          </button>
        </div>
      </header>

      {manifestState.status === "loading" && !manifestState.data ? (
        <div className="rendered-node-shell-state rendered-node-loading-shell">
          <div className="rendered-node-loading-backdrop" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <RenderedNodeLoadingOverlay label="Loading manifest" />
        </div>
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
        <div className={`rendered-node-content-wrap${loadingClass(manifestState.status === "loading")}`}>
          <div className="rendered-node-loading-content">
            <nav className="rendered-node-tabs" aria-label="Node UI pages" role="tablist">
              {manifest.pages.map((page) => (
                <button
                  key={page.id}
                  type="button"
                  role="tab"
                  aria-selected={page.id === activePage.id}
                  className={page.id === activePage.id ? "is-active" : ""}
                  onClick={() => setSelectedPageId(page.id)}
                >
                  <span className="rendered-node-tab-title">{page.title}</span>
                </button>
              ))}
            </nav>

            {activePage.page_endpoint ? (
              <PageSnapshotSection nodeId={nodeId} page={activePage} />
            ) : (
              <section className="rendered-node-page-section">
                <div className="rendered-node-surface-grid">
                  {resolveNodeUiPageSurfaces(activePage).map((surface) => (
                    <SurfaceCard key={surface.id} nodeId={nodeId} surface={surface} />
                  ))}
                </div>
              </section>
            )}
          </div>
          {manifestState.status === "loading" ? <RenderedNodeLoadingOverlay label="Refreshing manifest" /> : null}
        </div>
      ) : (
        <div className="rendered-node-shell-state rendered-node-shell-error">Manifest has no pages.</div>
      )}
    </section>
  );
}
