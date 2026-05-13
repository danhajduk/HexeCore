from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.reverse_proxy import ReverseProxyService
from app.ui_metadata import derive_node_api_base_url

from .service import NodesDomainService
from .ui_manifest import NodeUiManifest, NodeUiManifestValidationError, validate_node_ui_manifest


NODE_UI_MANIFEST_ENDPOINT_PATH = "node/ui-manifest"
NODE_UI_MANIFEST_TIMEOUT_SECONDS = 5.0

NodeUiManifestFetchStatus = Literal[
    "available",
    "node_not_found",
    "node_not_trusted",
    "endpoint_not_configured",
    "fetch_failed",
    "invalid_manifest",
]


def _text_attr(obj: object, name: str) -> str | None:
    value = str(getattr(obj, name, "") or "").strip()
    return value or None


def _node_runtime_api_base_url(node: object) -> str | None:
    runtime = getattr(node, "runtime", None)
    return derive_node_api_base_url(
        api_base_url=_text_attr(node, "api_base_url")
        or _text_attr(node, "requested_api_base_url")
        or _text_attr(runtime, "api_base_url"),
        ui_base_url=_text_attr(node, "ui_base_url") or _text_attr(runtime, "ui_base_url"),
        requested_ui_endpoint=_text_attr(node, "requested_ui_endpoint"),
        requested_hostname=_text_attr(node, "requested_hostname"),
    )


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, str(default)).strip()))
    except Exception:
        return default


class NodeUiManifestFetchResponse(BaseModel):
    node_id: str
    ok: bool
    status: NodeUiManifestFetchStatus
    manifest: dict[str, Any] | None = None
    manifest_revision: str | None = None
    cached: bool = False
    cached_manifest_revision: str | None = None
    error_code: str | None = None
    detail: str | None = None
    endpoint_path: str = Field(default="/api/node/ui-manifest")


class NodeUiManifestFetchService:
    def __init__(self, nodes_service: NodesDomainService, client: httpx.AsyncClient | None = None) -> None:
        self._nodes_service = nodes_service
        self._client = client
        self._cache: dict[tuple[str, str], NodeUiManifest] = {}
        self._latest_cache_key: dict[str, tuple[str, str]] = {}

    def cached_manifest(self, node_id: str, manifest_revision: str | None = None) -> NodeUiManifest | None:
        if manifest_revision is not None:
            return self._cache.get((node_id, manifest_revision))
        latest_key = self._latest_cache_key.get(node_id)
        if latest_key is None:
            return None
        return self._cache.get(latest_key)

    async def fetch_manifest(self, node_id: str) -> NodeUiManifestFetchResponse:
        try:
            node = self._nodes_service.get_node(node_id)
        except HTTPException as exc:
            if exc.status_code == 404:
                return self._error(node_id, "node_not_found", "node_not_found", "Node is not registered.")
            raise

        trust_status = str(getattr(getattr(node, "status", None), "trust_status", "") or "").strip().lower()
        if trust_status != "trusted":
            return self._error(
                node_id,
                "node_not_trusted",
                "node_not_trusted",
                "Core only fetches rendered UI manifests from trusted nodes.",
            )

        api_base = _node_runtime_api_base_url(node)
        if not api_base:
            return self._error(
                node_id,
                "endpoint_not_configured",
                "node_api_endpoint_not_configured",
                "Node does not have an API base URL for Core manifest discovery.",
            )

        target_url = ReverseProxyService.build_target_url(api_base, NODE_UI_MANIFEST_ENDPOINT_PATH)
        try:
            response = await self._get(target_url)
        except httpx.HTTPError as exc:
            return self._error(node_id, "fetch_failed", "node_manifest_fetch_failed", str(exc))

        if response.status_code < 200 or response.status_code >= 300:
            return self._error(
                node_id,
                "fetch_failed",
                "node_manifest_http_error",
                f"Node manifest endpoint returned HTTP {response.status_code}.",
            )

        try:
            payload = response.json()
        except ValueError:
            return self._error(node_id, "invalid_manifest", "node_manifest_invalid_json", "Manifest response was not JSON.")

        if not isinstance(payload, dict):
            return self._error(
                node_id,
                "invalid_manifest",
                "node_manifest_not_object",
                "Manifest response must be a JSON object.",
            )

        try:
            manifest = validate_node_ui_manifest(payload)
        except NodeUiManifestValidationError as exc:
            return self._error(node_id, "invalid_manifest", "manifest_validation_failed", str(exc))

        cache_key = (node_id, manifest.manifest_revision or "__unversioned__")
        self._cache[cache_key] = manifest
        self._latest_cache_key[node_id] = cache_key
        return NodeUiManifestFetchResponse(
            node_id=node_id,
            ok=True,
            status="available",
            manifest=manifest.to_payload(),
            manifest_revision=manifest.manifest_revision,
            cached=False,
            cached_manifest_revision=manifest.manifest_revision,
        )

    async def _get(self, target_url: str) -> httpx.Response:
        headers = {"Accept": "application/json"}
        if self._client is not None:
            return await self._client.get(target_url, headers=headers)
        timeout = httpx.Timeout(_env_float("SYNTHIA_NODE_UI_MANIFEST_TIMEOUT_SECONDS", NODE_UI_MANIFEST_TIMEOUT_SECONDS))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            return await client.get(target_url, headers=headers)

    def _error(
        self,
        node_id: str,
        status: NodeUiManifestFetchStatus,
        error_code: str,
        detail: str,
    ) -> NodeUiManifestFetchResponse:
        cached = self.cached_manifest(node_id)
        return NodeUiManifestFetchResponse(
            node_id=node_id,
            ok=False,
            status=status,
            error_code=error_code,
            detail=detail,
            cached_manifest_revision=cached.manifest_revision if cached is not None else None,
        )
