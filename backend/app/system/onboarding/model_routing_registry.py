from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODEL_ROUTING_REGISTRY_SCHEMA_VERSION = "1"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    # backend/app/system/onboarding/model_routing_registry.py -> onboarding(0), system(1), app(2), backend(3), repo(4)
    return Path(__file__).resolve().parents[4]


@dataclass
class ModelRoutingRecord:
    node_id: str
    provider: str
    model_id: str
    normalized_model_id: str
    pricing: dict[str, float]
    latency_metrics: dict[str, float]
    node_available: bool
    source: str
    updated_at: str
    schema_version: str = MODEL_ROUTING_REGISTRY_SCHEMA_VERSION

    @property
    def key(self) -> str:
        return f"{self.node_id}:{self.provider}:{self.normalized_model_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "provider": self.provider,
            "model_id": self.model_id,
            "normalized_model_id": self.normalized_model_id,
            "pricing": dict(self.pricing or {}),
            "latency_metrics": dict(self.latency_metrics or {}),
            "node_available": bool(self.node_available),
            "source": self.source,
            "updated_at": self.updated_at,
        }


class ModelRoutingRegistryStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_repo_root() / "data" / "model_routing_registry.json")
        self._items: dict[str, ModelRoutingRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        items = raw.get("items")
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("node_id") or "").strip()
            provider = str(item.get("provider") or "").strip().lower()
            model_id = str(item.get("model_id") or "").strip()
            normalized_model_id = str(item.get("normalized_model_id") or "").strip().lower()
            if not (node_id and provider and model_id and normalized_model_id):
                continue
            record = ModelRoutingRecord(
                node_id=node_id,
                provider=provider,
                model_id=model_id,
                normalized_model_id=normalized_model_id,
                pricing={str(k): float(v) for k, v in dict(item.get("pricing") or {}).items()},
                latency_metrics={str(k): float(v) for k, v in dict(item.get("latency_metrics") or {}).items()},
                node_available=bool(item.get("node_available")),
                source=str(item.get("source") or "unknown"),
                updated_at=str(item.get("updated_at") or _utcnow_iso()),
                schema_version=str(item.get("schema_version") or MODEL_ROUTING_REGISTRY_SCHEMA_VERSION),
            )
            self._items[record.key] = record

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": MODEL_ROUTING_REGISTRY_SCHEMA_VERSION,
            "items": [item.to_dict() for item in sorted(self._items.values(), key=lambda x: (x.node_id, x.provider, x.normalized_model_id))],
        }
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def upsert(self, record: ModelRoutingRecord) -> ModelRoutingRecord:
        self._items[record.key] = record
        self._save()
        return record

    def list(self, *, node_id: str | None = None, provider: str | None = None) -> list[ModelRoutingRecord]:
        node_filter = str(node_id or "").strip()
        provider_filter = str(provider or "").strip().lower()
        out: list[ModelRoutingRecord] = []
        for item in sorted(self._items.values(), key=lambda x: (x.node_id, x.provider, x.normalized_model_id)):
            if node_filter and item.node_id != node_filter:
                continue
            if provider_filter and item.provider != provider_filter:
                continue
            out.append(item)
        return out


class ModelRoutingRegistryService:
    def __init__(self, store: ModelRoutingRegistryStore) -> None:
        self._store = store

    def record_provider_intelligence(
        self,
        *,
        node_id: str,
        provider_intelligence: list[dict[str, Any]],
        node_available: bool,
        source: str,
    ) -> list[ModelRoutingRecord]:
        now = _utcnow_iso()
        out: list[ModelRoutingRecord] = []
        for provider_item in list(provider_intelligence or []):
            if not isinstance(provider_item, dict):
                continue
            provider = str(provider_item.get("provider") or "").strip().lower()
            if not provider:
                continue
            models = provider_item.get("available_models")
            if not isinstance(models, list):
                continue
            for model_item in models:
                if not isinstance(model_item, dict):
                    continue
                model_id = str(model_item.get("model_id") or "").strip()
                normalized_model_id = str(model_item.get("normalized_model_id") or model_id).strip().lower()
                if not (model_id and normalized_model_id):
                    continue
                pricing = {
                    str(k): float(v)
                    for k, v in dict(model_item.get("pricing") or {}).items()
                    if str(k or "").strip()
                }
                latency_metrics = {
                    str(k): float(v)
                    for k, v in dict(model_item.get("latency_metrics") or {}).items()
                    if str(k or "").strip()
                }
                record = ModelRoutingRecord(
                    node_id=str(node_id or "").strip(),
                    provider=provider,
                    model_id=model_id,
                    normalized_model_id=normalized_model_id,
                    pricing=pricing,
                    latency_metrics=latency_metrics,
                    node_available=bool(node_available),
                    source=str(source or "").strip() or "unknown",
                    updated_at=now,
                )
                out.append(self._store.upsert(record))
        return out

    def list(self, *, node_id: str | None = None, provider: str | None = None) -> list[ModelRoutingRecord]:
        return self._store.list(node_id=node_id, provider=provider)

    def find_model(
        self,
        *,
        node_id: str,
        provider: str,
        model_id: str,
    ) -> ModelRoutingRecord | None:
        node_key = str(node_id or "").strip()
        provider_key = str(provider or "").strip().lower()
        model_key = str(model_id or "").strip().lower()
        if not (node_key and provider_key and model_key):
            return None
        for item in self._store.list(node_id=node_key, provider=provider_key):
            if item.normalized_model_id == model_key or item.model_id.strip().lower() == model_key:
                return item
        return None

    def list_grouped_by_node(self, *, node_id: str | None = None, provider: str | None = None) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, list[ModelRoutingRecord]]] = {}
        availability: dict[str, bool] = {}
        for item in self.list(node_id=node_id, provider=provider):
            grouped.setdefault(item.node_id, {}).setdefault(item.provider, []).append(item)
            availability[item.node_id] = bool(item.node_available)
        out: list[dict[str, Any]] = []
        for nid in sorted(grouped.keys()):
            providers: list[dict[str, Any]] = []
            for pid in sorted(grouped[nid].keys()):
                models = [
                    model.to_dict()
                    for model in sorted(grouped[nid][pid], key=lambda x: x.normalized_model_id)
                ]
                providers.append({"provider": pid, "models": models})
            out.append({"node_id": nid, "node_available": availability.get(nid, False), "providers": providers})
        return out
