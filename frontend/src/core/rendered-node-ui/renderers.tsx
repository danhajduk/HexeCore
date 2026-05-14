import { useState, type ComponentType, type ReactNode } from "react";
import { Activity, AlertTriangle, CircleHelp, Play, RotateCw, Square, X } from "lucide-react";

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
  NodeUiRecordValue,
  NodeUiSurface,
  NodeUiTone,
  ProviderStatusCardResponse,
  RecordListCardResponse,
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

function formatRecordValue(value: NodeUiRecordValue): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function readRecordValue(value: unknown): NodeUiRecordValue {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean" || value == null) return value;
  return null;
}

function formatUpdatedAt(value?: string | null): string {
  if (!value) return "";
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return value;
  return new Date(parsed).toLocaleString();
}

type HealthStripItemPayload = NonNullable<HealthStripCardResponse["items"]>[number];
type RuntimeServicePayload = NonNullable<RuntimeServiceCardResponse["services"]>[number];
type ProviderStatusPayload = NonNullable<ProviderStatusCardResponse["providers"]>[number];

function healthStateName(item: HealthStripItemPayload): string {
  const legacy = item as typeof item & { label?: string | null };
  return String(item.state_name || legacy.label || "-").trim() || "-";
}

function healthCurrentState(item: HealthStripItemPayload): string {
  const legacy = item as typeof item & { value?: string | null };
  return String(item.current_state || legacy.value || "-").trim() || "-";
}

function formatPercent(value: unknown): string | null {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return `${number.toFixed(number >= 10 ? 1 : 2)}%`;
}

function formatBytes(value: unknown): string | null {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return null;
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
}

function compactFacts(facts: Array<NodeUiFact | null | undefined>): NodeUiFact[] {
  return facts.filter((fact): fact is NodeUiFact => Boolean(fact && fact.value !== null && fact.value !== undefined && fact.value !== ""));
}

function summaryFacts(summary?: Record<string, NodeUiRecordValue>): NodeUiFact[] {
  return Object.entries(summary || {}).map(([id, value]) => ({ id, label: labelize(id), value: formatRecordValue(value) }));
}

function runtimeServiceFacts(service: RuntimeServicePayload): NodeUiFact[] {
  const resourceUsage = service.resource_usage || {};
  return compactFacts([
    ...(service.facts || []),
    service.provider ? { id: `${service.id}.provider`, label: "Provider", value: service.provider } : null,
    service.model ? { id: `${service.id}.model`, label: "Model", value: service.model } : null,
    {
      id: `${service.id}.cpu`,
      label: "CPU",
      value: formatPercent(resourceUsage.process_cpu_percent ?? resourceUsage.cpu_percent),
    },
    {
      id: `${service.id}.rss`,
      label: "Memory",
      value: formatBytes(resourceUsage.process_memory_rss_bytes) || readRecordValue(resourceUsage.memory_usage),
    },
    { id: `${service.id}.load`, label: "Load 1m", value: resourceUsage.system_load_1m as string | number | null },
  ]);
}

function providerStatusFacts(provider: ProviderStatusPayload): NodeUiFact[] {
  return compactFacts([
    provider.provider ? { id: `${provider.id}.provider`, label: "Provider", value: provider.provider } : null,
    ...(provider.facts || []),
    ...(provider.quotas || []),
  ]);
}

function providerSummary(provider: ProviderStatusPayload): string {
  if (provider.provider) return provider.provider;
  const firstFact = [...(provider.facts || []), ...(provider.quotas || [])].find(
    (fact) => fact.value !== null && fact.value !== undefined && fact.value !== "",
  );
  if (firstFact) return formatValue(firstFact.value, firstFact.unit);
  if (provider.errors && provider.errors.length > 0) return "Needs attention";
  return "Details available";
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
  const disabledReason = action.disabled_reason || action.reason;
  const actionName = `${action.id} ${action.label || ""}`.toLowerCase();
  const ActionIcon = actionName.includes("restart")
    ? RotateCw
    : actionName.includes("start")
      ? Play
      : actionName.includes("stop")
        ? Square
        : RotateCw;
  return (
    <button
      type="button"
      className={`rendered-node-action ${toneClass(action.tone)}`}
      disabled={!enabled}
      title={disabledReason || action.label || action.id}
      onClick={() => {
        if (enabled) onAction?.(action, surface);
      }}
    >
      <ActionIcon size={15} aria-hidden="true" />
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
          {(data.items || []).map((item, index) => {
            const stateName = healthStateName(item);
            const currentState = healthCurrentState(item);
            return (
              <div key={`${stateName}-${index}`} className={`rendered-node-health-item ${toneClass(item.tone)}`}>
                <span>{stateName}</span>
                <strong>{currentState}</strong>
              </div>
            );
          })}
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

export function RecordListCard({ surface, data }: NodeUiCardRendererProps<RecordListCardResponse>) {
  const records = data.records || [];
  const columns = data.columns || [];
  return (
    <CardShell surface={surface} data={data}>
      {data.summary ? <FactGrid facts={summaryFacts(data.summary)} /> : null}
      <div className="rendered-node-record-list">
        {records.map((record) => {
          const title = formatRecordValue(
            readRecordValue(record.name) || readRecordValue(record.session_id) || readRecordValue(record.endpoint_id) || record.id,
          );
          const status = formatRecordValue(readRecordValue(record.status));
          return (
            <section key={record.id} className={`rendered-node-record-item ${record.active ? "is-active" : ""}`}>
              <div className="rendered-node-record-main">
                <div>
                  <h4>{title}</h4>
                  {record.active ? <span className="rendered-node-record-active">Active</span> : null}
                </div>
                {record.status ? <span className={`rendered-node-pill ${toneClass(record.tone)}`}>{labelize(status)}</span> : null}
              </div>
              <dl className="rendered-node-record-fields">
                {columns
                  .filter((column) => column.id !== "name" && column.id !== "session_id" && column.id !== "status")
                  .map((column) => (
                    <div key={column.id}>
                      <dt>{column.label}</dt>
                      <dd>{formatRecordValue(readRecordValue(record[column.id]))}</dd>
                    </div>
                  ))}
              </dl>
            </section>
          );
        })}
      </div>
    </CardShell>
  );
}

export function RuntimeServiceCard({ surface, data, onAction }: NodeUiCardRendererProps<RuntimeServiceCardResponse>) {
  const [selectedService, setSelectedService] = useState<RuntimeServicePayload | null>(null);
  const selectedState = selectedService?.state || selectedService?.runtime_state || "unknown";
  const selectedTone =
    selectedService?.tone || selectedService?.health_status || (selectedService?.healthy === false ? "danger" : "neutral");

  return (
    <CardShell surface={surface} data={data}>
      <div className="rendered-node-runtime-grid">
        {(data.services || []).map((service) => {
          const state = service.state || service.runtime_state || "unknown";
          const tone = service.tone || service.health_status || (service.healthy === false ? "danger" : "neutral");
          const summary = service.provider || service.model || (service.last_error ? "Needs attention" : "Details available");
          return (
            <button
              key={service.id}
              type="button"
              className="rendered-node-runtime-item rendered-node-runtime-button"
              onClick={() => setSelectedService(service)}
              aria-label={`Open ${service.label} details`}
            >
              <div className="rendered-node-list-head">
                <Activity size={18} aria-hidden="true" />
                <div>
                  <h4>{service.label}</h4>
                  <span className={`rendered-node-pill ${toneClass(tone)}`}>{labelize(state)}</span>
                </div>
              </div>
              <span className="rendered-node-runtime-summary">{summary}</span>
              <span className="rendered-node-runtime-details-link">Details</span>
            </button>
          );
        })}
      </div>
      <ActionRow actions={data.actions} surface={surface} onAction={onAction} />
      {selectedService ? (
        <div className="rendered-node-dialog-backdrop" role="presentation" onClick={() => setSelectedService(null)}>
          <section
            className="rendered-node-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={`rendered-node-runtime-dialog-${selectedService.id}`}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="rendered-node-dialog-head">
              <div>
                <h3 id={`rendered-node-runtime-dialog-${selectedService.id}`}>{selectedService.label}</h3>
                <span className={`rendered-node-pill ${toneClass(selectedTone)}`}>{labelize(selectedState)}</span>
              </div>
              <button type="button" className="rendered-node-icon-button" onClick={() => setSelectedService(null)} title="Close">
                <X size={16} aria-hidden="true" />
              </button>
            </header>
            <FactGrid facts={runtimeServiceFacts(selectedService)} />
            {selectedService.last_error ? (
              <ErrorList errors={[{ code: `${selectedService.id}.last_error`, message: selectedService.last_error, tone: "danger" }]} />
            ) : null}
            <ActionRow actions={selectedService.actions} surface={surface} onAction={onAction} />
          </section>
        </div>
      ) : null}
    </CardShell>
  );
}

export function ProviderStatusCard({ surface, data, onAction }: NodeUiCardRendererProps<ProviderStatusCardResponse>) {
  const [selectedProvider, setSelectedProvider] = useState<ProviderStatusPayload | null>(null);
  const selectedState = selectedProvider?.state || "unknown";
  const selectedTone = selectedProvider?.tone || (selectedProvider?.errors?.length ? "danger" : "neutral");

  return (
    <CardShell surface={surface} data={data}>
      <div className="rendered-node-provider-grid">
        {(data.providers || []).map((provider) => {
          const state = provider.state || "unknown";
          return (
            <button
              key={provider.id}
              type="button"
              className="rendered-node-provider-item rendered-node-provider-button"
              onClick={() => setSelectedProvider(provider)}
              aria-label={`Open ${provider.label} details`}
            >
              <div className="rendered-node-list-head">
                <Activity size={18} aria-hidden="true" />
                <div>
                  <h4>{provider.label}</h4>
                  <span className={`rendered-node-pill ${toneClass(provider.tone)}`}>{labelize(state)}</span>
                </div>
              </div>
              <span className="rendered-node-runtime-summary">{providerSummary(provider)}</span>
              <span className="rendered-node-runtime-details-link">Details</span>
            </button>
          );
        })}
      </div>
      {selectedProvider ? (
        <div className="rendered-node-dialog-backdrop" role="presentation" onClick={() => setSelectedProvider(null)}>
          <section
            className="rendered-node-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={`rendered-node-provider-dialog-${selectedProvider.id}`}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="rendered-node-dialog-head">
              <div>
                <h3 id={`rendered-node-provider-dialog-${selectedProvider.id}`}>{selectedProvider.label}</h3>
                <span className={`rendered-node-pill ${toneClass(selectedTone)}`}>{labelize(selectedState)}</span>
              </div>
              <button type="button" className="rendered-node-icon-button" onClick={() => setSelectedProvider(null)} title="Close">
                <X size={16} aria-hidden="true" />
              </button>
            </header>
            <section className="rendered-node-dialog-section">
              <h4>Status</h4>
              <FactGrid facts={providerStatusFacts(selectedProvider)} />
              {selectedProvider.errors && selectedProvider.errors.length > 0 ? <ErrorList errors={selectedProvider.errors} /> : null}
            </section>
            <section className="rendered-node-dialog-section">
              <h4>Setup</h4>
              <FactGrid facts={selectedProvider.setup?.facts} />
              {selectedProvider.setup?.errors && selectedProvider.setup.errors.length > 0 ? (
                <ErrorList errors={selectedProvider.setup.errors} />
              ) : null}
              <ActionRow actions={selectedProvider.setup?.actions} surface={surface} onAction={onAction} />
            </section>
          </section>
        </div>
      ) : null}
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
  record_list: RecordListCard,
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
