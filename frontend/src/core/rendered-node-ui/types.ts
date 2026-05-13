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
