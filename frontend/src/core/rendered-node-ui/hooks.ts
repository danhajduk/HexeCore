import { useCallback, useEffect, useState } from "react";

import { fetchNodeSurfaceData, fetchNodeUiManifest } from "./api";
import type { NodeUiLoadState, NodeUiManifestFetchResponse } from "./types";

type ReloadableNodeUiLoadState<T> = NodeUiLoadState<T> & {
  reload: () => void;
};

function initialState<T>(): NodeUiLoadState<T> {
  return {
    status: "idle",
    data: null,
    error: null,
  };
}

export function useNodeUiManifest(
  nodeId: string,
  options: { enabled?: boolean } = {},
): ReloadableNodeUiLoadState<NodeUiManifestFetchResponse> {
  const [state, setState] = useState<NodeUiLoadState<NodeUiManifestFetchResponse>>(initialState);
  const [reloadKey, setReloadKey] = useState(0);
  const reload = useCallback(() => setReloadKey((value) => value + 1), []);
  const enabled = options.enabled ?? true;

  useEffect(() => {
    if (!enabled) {
      setState(initialState<NodeUiManifestFetchResponse>());
      return;
    }
    const target = String(nodeId || "").trim();
    if (!target) {
      setState({ status: "error", data: null, error: "node_id_required" });
      return;
    }

    const controller = new AbortController();
    setState((current) => ({ status: "loading", data: current.data, error: null }));

    fetchNodeUiManifest(target, { signal: controller.signal })
      .then((data) => {
        setState({ status: "ready", data, error: data.ok ? null : data.detail || data.error_code || data.status });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: "error", data: null, error: error instanceof Error ? error.message : String(error) });
      });

    return () => {
      controller.abort();
    };
  }, [nodeId, enabled, reloadKey]);

  return { ...state, reload };
}

export function useNodeSurfaceData<T>(
  nodeId: string,
  endpoint: string | null | undefined,
  options: { enabled?: boolean } = {},
): ReloadableNodeUiLoadState<T> {
  const [state, setState] = useState<NodeUiLoadState<T>>(initialState);
  const [reloadKey, setReloadKey] = useState(0);
  const reload = useCallback(() => setReloadKey((value) => value + 1), []);
  const enabled = options.enabled ?? true;

  useEffect(() => {
    const target = String(nodeId || "").trim();
    const dataEndpoint = String(endpoint || "").trim();
    if (!enabled) {
      setState(initialState<T>());
      return;
    }
    if (!target) {
      setState({ status: "error", data: null, error: "node_id_required" });
      return;
    }
    if (!dataEndpoint) {
      setState({ status: "error", data: null, error: "node_ui_endpoint_required" });
      return;
    }

    const controller = new AbortController();
    setState((current) => ({ status: "loading", data: current.data, error: null }));

    fetchNodeSurfaceData<T>(target, dataEndpoint, { signal: controller.signal })
      .then((data) => {
        setState({ status: "ready", data, error: null });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ status: "error", data: null, error: error instanceof Error ? error.message : String(error) });
      });

    return () => {
      controller.abort();
    };
  }, [nodeId, endpoint, enabled, reloadKey]);

  return { ...state, reload };
}
