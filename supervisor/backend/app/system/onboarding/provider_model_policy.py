from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PROVIDER_MODEL_POLICY_SCHEMA_VERSION = "1"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    # backend/app/system/onboarding/provider_model_policy.py -> onboarding(0), system(1), app(2), backend(3), repo(4)
    return Path(__file__).resolve().parents[4]


@dataclass
class ProviderModelPolicyRecord:
    provider: str
    allowed_models: list[str]
    updated_at: str
    updated_by: str | None = None
    schema_version: str = PROVIDER_MODEL_POLICY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "allowed_models": list(self.allowed_models or []),
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
        }


class ProviderModelPolicyStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_repo_root() / "data" / "provider_model_policy.json")
        self._records: dict[str, ProviderModelPolicyRecord] = {}
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
            provider = str(item.get("provider") or "").strip().lower()
            if not provider:
                continue
            models = item.get("allowed_models")
            allowed_models = [str(v).strip() for v in models] if isinstance(models, list) else []
            self._records[provider] = ProviderModelPolicyRecord(
                provider=provider,
                allowed_models=[model for model in allowed_models if model],
                updated_at=str(item.get("updated_at") or _utcnow_iso()),
                updated_by=str(item.get("updated_by") or "").strip() or None,
                schema_version=str(item.get("schema_version") or PROVIDER_MODEL_POLICY_SCHEMA_VERSION),
            )

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": PROVIDER_MODEL_POLICY_SCHEMA_VERSION,
            "items": [self._records[key].to_dict() for key in sorted(self._records.keys())],
        }
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def list(self) -> list[ProviderModelPolicyRecord]:
        return [self._records[key] for key in sorted(self._records.keys())]

    def get(self, provider: str) -> ProviderModelPolicyRecord | None:
        return self._records.get(str(provider or "").strip().lower())

    def upsert(self, *, provider: str, allowed_models: list[str], updated_by: str | None = None) -> ProviderModelPolicyRecord:
        provider_key = str(provider or "").strip().lower()
        if not provider_key:
            raise ValueError("provider_required")
        allowed = sorted({str(model or "").strip() for model in list(allowed_models or []) if str(model or "").strip()})
        record = ProviderModelPolicyRecord(
            provider=provider_key,
            allowed_models=allowed,
            updated_at=_utcnow_iso(),
            updated_by=(str(updated_by or "").strip() or None),
        )
        self._records[provider_key] = record
        self._save()
        return record

    def delete(self, provider: str) -> ProviderModelPolicyRecord | None:
        provider_key = str(provider or "").strip().lower()
        if not provider_key:
            return None
        removed = self._records.pop(provider_key, None)
        if removed is not None:
            self._save()
        return removed


class ProviderModelApprovalPolicyService:
    def __init__(self, store: ProviderModelPolicyStore) -> None:
        self._store = store

    def list(self) -> list[ProviderModelPolicyRecord]:
        return self._store.list()

    def get(self, provider: str) -> ProviderModelPolicyRecord | None:
        return self._store.get(provider)

    def set_allowlist(self, *, provider: str, allowed_models: list[str], updated_by: str | None = None) -> ProviderModelPolicyRecord:
        return self._store.upsert(provider=provider, allowed_models=allowed_models, updated_by=updated_by)

    def remove_provider(self, provider: str) -> ProviderModelPolicyRecord | None:
        return self._store.delete(provider)

    def is_model_allowed(self, *, provider: str, model_id: str) -> bool:
        record = self._store.get(provider)
        if record is None:
            return True
        return str(model_id or "").strip() in set(record.allowed_models or [])

    def has_explicit_policy(self, provider: str) -> bool:
        return self._store.get(provider) is not None
