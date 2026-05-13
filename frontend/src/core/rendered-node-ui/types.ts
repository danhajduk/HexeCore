export type NodeUiRefreshMode = "live" | "near_live" | "manual" | "detail" | "static";

export type NodeUiRefreshPolicy = {
  mode: NodeUiRefreshMode;
  interval_ms?: number | null;
  cache_ttl_ms?: number | null;
};

export type NodeUiActionMethod = "POST" | "PUT" | "PATCH" | "DELETE";

export type NodeUiActionConfirmation = {
  required?: boolean;
  title?: string | null;
  message?: string | null;
  tone?: "info" | "warning" | "danger";
};

export type NodeUiAction = {
  id: string;
  label: string;
  method: NodeUiActionMethod;
  endpoint: string;
  description?: string | null;
  request_schema?: Record<string, unknown>;
  destructive?: boolean;
  sensitive?: boolean;
  confirmation?: NodeUiActionConfirmation | null;
};

export type NodeUiSurface = {
  id: string;
  kind: string;
  title: string;
  data_endpoint: string;
  description?: string | null;
  detail_endpoint_template?: string | null;
  actions?: NodeUiAction[];
  refresh: NodeUiRefreshPolicy;
};

export type NodeUiPage = {
  id: string;
  title: string;
  description?: string | null;
  page_endpoint?: string | null;
  refresh?: NodeUiRefreshPolicy | null;
  surfaces: NodeUiSurface[];
};

export type NodeUiManifest = {
  schema_version: "1.0";
  manifest_revision?: string | null;
  node_id: string;
  node_type: string;
  display_name: string;
  pages: NodeUiPage[];
};

export type NodeUiManifestFetchStatus =
  | "available"
  | "node_not_found"
  | "node_not_trusted"
  | "endpoint_not_configured"
  | "fetch_failed"
  | "invalid_manifest";

export type NodeUiManifestFetchResponse = {
  node_id: string;
  ok: boolean;
  status: NodeUiManifestFetchStatus;
  manifest?: NodeUiManifest | null;
  manifest_revision?: string | null;
  cached?: boolean;
  cached_manifest_revision?: string | null;
  error_code?: string | null;
  detail?: string | null;
  endpoint_path?: string;
};

export type NodeUiLoadStatus = "idle" | "loading" | "ready" | "error";

export type NodeUiLoadState<T> = {
  status: NodeUiLoadStatus;
  data: T | null;
  error: string | null;
};

export type NodeUiTone = "neutral" | "info" | "success" | "warning" | "error" | "danger";

export type NodeUiCardError = {
  code: string;
  message: string;
  tone?: NodeUiTone;
  retryable?: boolean;
};

export type NodeUiRetryState = {
  retry_after_ms?: number | null;
  action_label?: string | null;
};

export type NodeUiCardResponseBase = {
  kind: string;
  updated_at: string;
  stale?: boolean;
  empty?: boolean;
  errors?: NodeUiCardError[];
  retry?: NodeUiRetryState | null;
};

export type NodeUiFact = {
  id: string;
  label: string;
  value?: string | number | boolean | null;
  unit?: string | null;
  tone?: NodeUiTone;
  detail?: string | null;
};

export type NodeOverviewCardResponse = NodeUiCardResponseBase & {
  kind: "node_overview";
  identity?: NodeUiFact[];
  lifecycle?: NodeUiFact[];
  trust?: NodeUiFact[];
  software?: NodeUiFact[];
  core_pairing?: NodeUiFact[];
};

export type HealthStripCardResponse = NodeUiCardResponseBase & {
  kind: "health_strip";
  items?: Array<{
    id: string;
    label: string;
    value: string;
    tone?: NodeUiTone;
    detail?: string | null;
  }>;
};

export type FactsCardResponse = NodeUiCardResponseBase & {
  kind: "facts_card";
  title?: string | null;
  facts?: NodeUiFact[];
};

export type NodeUiActionState = {
  id: string;
  label?: string | null;
  enabled?: boolean;
  reason?: string | null;
  tone?: NodeUiTone;
};

export type WarningBannerCardResponse = NodeUiCardResponseBase & {
  kind: "warning_banner";
  warnings?: Array<{
    id: string;
    title: string;
    message?: string | null;
    tone?: NodeUiTone;
    actions?: NodeUiActionState[];
  }>;
};

export type ActionPanelCardResponse = NodeUiCardResponseBase & {
  kind: "action_panel";
  groups?: Array<{
    id: string;
    label: string;
    actions?: NodeUiActionState[];
  }>;
};

export type RuntimeServiceCardResponse = NodeUiCardResponseBase & {
  kind: "runtime_service";
  actions?: NodeUiActionState[];
  supervisor?: Record<string, unknown>;
  services?: Array<{
    id: string;
    label: string;
    state?: string | null;
    tone?: NodeUiTone;
    healthy?: boolean;
    provider?: string | null;
    model?: string | null;
    resource_usage?: Record<string, unknown>;
    last_error?: string | null;
    restart_supported?: boolean;
    restart_target?: string | null;
    runtime_state?: "unknown" | "stopped" | "starting" | "running" | "degraded" | "error";
    health_status?: NodeUiTone;
    facts?: NodeUiFact[];
    actions?: NodeUiActionState[];
  }>;
};

export type ProviderStatusCardResponse = NodeUiCardResponseBase & {
  kind: "provider_status";
  providers?: Array<{
    id: string;
    label: string;
    provider?: string | null;
    state?: "unknown" | "ready" | "degraded" | "unavailable" | "disabled" | "error";
    tone?: NodeUiTone;
    facts?: NodeUiFact[];
    quotas?: NodeUiFact[];
    errors?: NodeUiCardError[];
  }>;
};

export type NodeUiCardResponse =
  | NodeOverviewCardResponse
  | HealthStripCardResponse
  | FactsCardResponse
  | WarningBannerCardResponse
  | ActionPanelCardResponse
  | RuntimeServiceCardResponse
  | ProviderStatusCardResponse;

export type NodeUiPageCard = {
  id: string;
  kind: string;
  title?: string | null;
  description?: string | null;
  detail_endpoint_template?: string | null;
  actions?: NodeUiAction[];
  refresh?: NodeUiRefreshPolicy | null;
  data: NodeUiCardResponse;
};

export type NodeUiPageSnapshot = {
  page_id: string;
  updated_at?: string | null;
  refresh?: NodeUiRefreshPolicy | null;
  cards: NodeUiPageCard[];
};
