import type { ComponentType, ReactNode } from "react";
import { Activity, AlertTriangle, CircleHelp, RotateCw } from "lucide-react";

import type {
  ActionPanelCardResponse,
  FactsCardResponse,
  HealthStripCardResponse,
  NodeOverviewCardResponse,
  NodeUiActionState,
  NodeUiCardError,
  NodeUiCardResponse,
  NodeUiCardResponseBase,
  NodeUiFact,
  NodeUiSurface,
  NodeUiTone,
  ProviderStatusCardResponse,
  RuntimeServiceCardResponse,
  WarningBannerCardResponse,
} from "./types";
import "./rendered-node-ui.css";

type ActionHandler = (action: NodeUiActionState, surface: NodeUiSurface) => void;

export type NodeUiCardRendererProps<T extends NodeUiCardResponse = NodeUiCardResponse> = {
  surface: NodeUiSurface;
  data: T;
  onAction?: ActionHandler;
};

export type NodeUiCardRenderer<T extends NodeUiCardResponse = NodeUiCardResponse> = ComponentType<
  NodeUiCardRendererProps<T>
>;

function toneClass(tone?: NodeUiTone | string | null): string {
  const value = String(tone || "neutral").trim().toLowerCase();
  if (["info", "success", "warning", "error", "danger"].includes(value)) return `tone-${value}`;
  return "tone-neutral";
}

function labelize(value?: string | null): string {
  const text = String(value || "").trim();
  if (!text) return "-";
  return text.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatValue(value: NodeUiFact["value"], unit?: string | null): string {
  if (value === null || value === undefined || value === "") return "-";
  const text = typeof value === "boolean" ? (value ? "Yes" : "No") : String(value);
  return unit ? `${text} ${unit}` : text;
}

function formatUpdatedAt(value?: string | null): string {
  if (!value) return "";
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return value;
  return new Date(parsed).toLocaleString();
}

function CardShell({
  surface,
  data,
  children,
}: {
  surface: NodeUiSurface;
  data: NodeUiCardResponseBase;
  children: ReactNode;
}) {
  const errors = data.errors || [];
  const stateClass = [data.stale ? "is-stale" : "", data.empty ? "is-empty" : ""].filter(Boolean).join(" ");
  return (
    <article className={`rendered-node-card kind-${surface.kind} ${stateClass}`}>
      <header className="rendered-node-card-head">
        <div>
          <h3>{surface.title}</h3>
          {surface.description ? <p>{surface.description}</p> : null}
        </div>
        <div className="rendered-node-card-meta">
          {data.stale ? <span className="rendered-node-pill tone-warning">Stale</span> : null}
          {data.updated_at ? <time>{formatUpdatedAt(data.updated_at)}</time> : null}
        </div>
      </header>
      {errors.length > 0 ? <ErrorList errors={errors} /> : null}
      {data.empty ? <div className="rendered-node-empty">No data.</div> : children}
    </article>
  );
}

function ErrorList({ errors }: { errors: NodeUiCardError[] }) {
  return (
    <div className="rendered-node-errors">
      {errors.map((error) => (
        <div key={error.code} className={`rendered-node-error ${toneClass(error.tone)}`}>
          <AlertTriangle size={16} aria-hidden="true" />
          <span>{error.message}</span>
        </div>
      ))}
    </div>
  );
}

function FactGrid({ facts }: { facts?: NodeUiFact[] }) {
  const items = facts || [];
  if (items.length === 0) return <div className="rendered-node-empty">No data.</div>;
  return (
    <dl className="rendered-node-fact-grid">
      {items.map((fact) => (
        <div key={fact.id} className={`rendered-node-fact ${toneClass(fact.tone)}`}>
          <dt>{fact.label}</dt>
          <dd>{formatValue(fact.value, fact.unit)}</dd>
          {fact.detail ? <span>{fact.detail}</span> : null}
        </div>
      ))}
    </dl>
  );
}

function ActionButton({
  action,
  surface,
  onAction,
}: {
  action: NodeUiActionState;
  surface: NodeUiSurface;
  onAction?: ActionHandler;
}) {
  const enabled = action.enabled !== false && Boolean(onAction);
  return (
    <button
      type="button"
      className={`rendered-node-action ${toneClass(action.tone)}`}
      disabled={!enabled}
      title={action.reason || action.label || action.id}
      onClick={() => {
        if (enabled) onAction?.(action, surface);
      }}
    >
      <RotateCw size={15} aria-hidden="true" />
      <span>{action.label || labelize(action.id)}</span>
    </button>
  );
}

function ActionRow({
  actions,
  surface,
  onAction,
}: {
  actions?: NodeUiActionState[];
  surface: NodeUiSurface;
  onAction?: ActionHandler;
}) {
  const items = actions || [];
  if (items.length === 0) return null;
  return (
    <div className="rendered-node-actions">
      {items.map((action) => (
        <ActionButton key={action.id} action={action} surface={surface} onAction={onAction} />
      ))}
    </div>
  );
}

export function NodeOverviewCard({ surface, data }: NodeUiCardRendererProps<NodeOverviewCardResponse>) {
  const groups: Array<[string, NodeUiFact[] | undefined]> = [
    ["Identity", data.identity],
    ["Lifecycle", data.lifecycle],
    ["Trust", data.trust],
    ["Software", data.software],
    ["Core Pairing", data.core_pairing],
  ];
  return (
    <CardShell surface={surface} data={data}>
      <div className="rendered-node-overview-groups">
        {groups.map(([label, facts]) =>
          facts && facts.length > 0 ? (
            <section key={label} className="rendered-node-subsection">
              <h4>{label}</h4>
              <FactGrid facts={facts} />
            </section>
          ) : null,
        )}
      </div>
    </CardShell>
  );
}

export function HealthStripCard({ surface, data }: NodeUiCardRendererProps<HealthStripCardResponse>) {
  const errors = data.errors || [];
  return (
    <article className={`rendered-node-card kind-${surface.kind} ${data.stale ? "is-stale" : ""}`}>
      {errors.length > 0 ? <ErrorList errors={errors} /> : null}
      {data.empty ? (
        <div className="rendered-node-empty">No data.</div>
      ) : (
        <div className="rendered-node-health-strip">
          {(data.items || []).map((item) => (
            <div key={item.id} className={`rendered-node-health-item ${toneClass(item.tone)}`}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              {item.detail ? <small>{item.detail}</small> : null}
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

export function FactsCard({ surface, data }: NodeUiCardRendererProps<FactsCardResponse>) {
  return (
    <CardShell surface={surface} data={data}>
      {data.title ? <h4 className="rendered-node-inline-title">{data.title}</h4> : null}
      <FactGrid facts={data.facts} />
    </CardShell>
  );
}

export function WarningBannerCard({ surface, data, onAction }: NodeUiCardRendererProps<WarningBannerCardResponse>) {
  const warnings = data.warnings || [];
  return (
    <CardShell surface={surface} data={data}>
      <div className="rendered-node-warning-list">
        {warnings.map((warning) => (
          <section key={warning.id} className={`rendered-node-warning ${toneClass(warning.tone)}`}>
            <div className="rendered-node-warning-copy">
              <span className="rendered-node-warning-icon">
                <AlertTriangle size={16} aria-hidden="true" />
              </span>
              <div>
                <h4>{warning.title || labelize(warning.id)}</h4>
                {warning.message ? <p>{warning.message}</p> : null}
              </div>
            </div>
            <ActionRow actions={warning.actions} surface={surface} onAction={onAction} />
          </section>
        ))}
      </div>
    </CardShell>
  );
}

export function ActionPanelCard({ surface, data, onAction }: NodeUiCardRendererProps<ActionPanelCardResponse>) {
  return (
    <CardShell surface={surface} data={data}>
      <div className="rendered-node-action-groups">
        {(data.groups || []).map((group) => (
          <section key={group.id} className="rendered-node-action-group">
            <h4>{group.label}</h4>
            <ActionRow actions={group.actions} surface={surface} onAction={onAction} />
          </section>
        ))}
      </div>
    </CardShell>
  );
}

export function RuntimeServiceCard({ surface, data, onAction }: NodeUiCardRendererProps<RuntimeServiceCardResponse>) {
  return (
    <CardShell surface={surface} data={data}>
      <div className="rendered-node-list">
        {(data.services || []).map((service) => (
          <section key={service.id} className="rendered-node-list-item">
            <div className="rendered-node-list-head">
              <Activity size={18} aria-hidden="true" />
              <div>
                <h4>{service.label}</h4>
                <span className={`rendered-node-pill ${toneClass(service.health_status)}`}>
                  {labelize(service.runtime_state)}
                </span>
              </div>
            </div>
            <FactGrid facts={service.facts} />
            <ActionRow actions={service.actions} surface={surface} onAction={onAction} />
          </section>
        ))}
      </div>
    </CardShell>
  );
}

export function ProviderStatusCard({ surface, data }: NodeUiCardRendererProps<ProviderStatusCardResponse>) {
  return (
    <CardShell surface={surface} data={data}>
      <div className="rendered-node-list">
        {(data.providers || []).map((provider) => (
          <section key={provider.id} className="rendered-node-list-item">
            <div className="rendered-node-list-head">
              <Activity size={18} aria-hidden="true" />
              <div>
                <h4>{provider.label}</h4>
                <span className={`rendered-node-pill ${toneClass(provider.tone)}`}>{labelize(provider.state)}</span>
              </div>
            </div>
            {provider.provider ? <p className="rendered-node-muted">{provider.provider}</p> : null}
            <FactGrid facts={[...(provider.facts || []), ...(provider.quotas || [])]} />
            {provider.errors && provider.errors.length > 0 ? <ErrorList errors={provider.errors} /> : null}
          </section>
        ))}
      </div>
    </CardShell>
  );
}

export function UnsupportedNodeUiCard({ surface, data }: NodeUiCardRendererProps<NodeUiCardResponse>) {
  return (
    <article className="rendered-node-card rendered-node-card-unsupported">
      <CircleHelp size={18} aria-hidden="true" />
      <div>
        <h3>{surface.title}</h3>
        <p>{`Unsupported card kind: ${data.kind || surface.kind}`}</p>
      </div>
    </article>
  );
}

export const NODE_UI_CARD_RENDERERS: Record<string, NodeUiCardRenderer<any>> = {
  node_overview: NodeOverviewCard,
  health_strip: HealthStripCard,
  facts_card: FactsCard,
  warning_banner: WarningBannerCard,
  action_panel: ActionPanelCard,
  runtime_service: RuntimeServiceCard,
  provider_status: ProviderStatusCard,
};

export function getNodeUiCardRenderer(kind: string): NodeUiCardRenderer<any> {
  return NODE_UI_CARD_RENDERERS[String(kind || "").trim()] || UnsupportedNodeUiCard;
}

export function NodeUiCard({ surface, data, onAction }: NodeUiCardRendererProps<NodeUiCardResponse>) {
  const Renderer = getNodeUiCardRenderer(data.kind || surface.kind);
  return <Renderer surface={surface} data={data as any} onAction={onAction} />;
}
