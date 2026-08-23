from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .model_routing_registry import ModelRoutingRegistryService


NODE_BUDGET_SCHEMA_VERSION = "1"
ALLOCATION_KINDS = {"customer", "provider"}
GRANT_STATUSES = {"active", "revoked", "expired"}
SUPPORTED_PERIODS = {"monthly", "daily", "manual_reset"}
SUPPORTED_RESET_POLICIES = {"calendar", "rolling", "manual"}
SUPPORTED_ENFORCEMENT_MODES = {"hard_stop", "warn"}
SUPPORTED_COMPUTE_UNITS = {"cost_units", "tokens", "requests", "gpu_seconds", "cpu_seconds"}
DEFAULT_BUDGET_ALERT_THRESHOLDS = (0.8, 0.9, 1.0)
NODE_BUDGET_SERVICE_ID = "ai.inference"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _clean_text(value: Any, *, lower: bool = False) -> str:
    text = str(value or "").strip()
    return text.lower() if lower else text


def _coerce_optional_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    amount = float(value)
    if amount < 0:
        raise ValueError("budget_value_must_be_non_negative")
    return amount


@dataclass
class NodeBudgetCapabilityRecord:
    node_id: str
    currency: str
    compute_unit: str
    default_period: str
    supports_money_budget: bool
    supports_compute_budget: bool
    supports_customer_allocations: bool
    supports_provider_allocations: bool
    supported_providers: list[str] = field(default_factory=list)
    setup_requirements: list[str] = field(default_factory=list)
    suggested_money_limit: float | None = None
    suggested_compute_limit: float | None = None
    declared_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)
    schema_version: str = NODE_BUDGET_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "currency": self.currency,
            "compute_unit": self.compute_unit,
            "default_period": self.default_period,
            "supports_money_budget": self.supports_money_budget,
            "supports_compute_budget": self.supports_compute_budget,
            "supports_customer_allocations": self.supports_customer_allocations,
            "supports_provider_allocations": self.supports_provider_allocations,
            "supported_providers": list(self.supported_providers or []),
            "setup_requirements": list(self.setup_requirements or []),
            "suggested_money_limit": self.suggested_money_limit,
            "suggested_compute_limit": self.suggested_compute_limit,
            "declared_at": self.declared_at,
            "updated_at": self.updated_at,
        }


@dataclass
class NodeBudgetConfigRecord:
    node_id: str
    currency: str
    compute_unit: str
    period: str
    reset_policy: str
    enforcement_mode: str
    overcommit_enabled: bool
    shared_customer_pool: bool
    shared_provider_pool: bool
    node_money_limit: float | None = None
    node_compute_limit: float | None = None
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)
    schema_version: str = NODE_BUDGET_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "currency": self.currency,
            "compute_unit": self.compute_unit,
            "period": self.period,
            "reset_policy": self.reset_policy,
            "enforcement_mode": self.enforcement_mode,
            "overcommit_enabled": self.overcommit_enabled,
            "shared_customer_pool": self.shared_customer_pool,
            "shared_provider_pool": self.shared_provider_pool,
            "node_money_limit": self.node_money_limit,
            "node_compute_limit": self.node_compute_limit,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class NodeBudgetAllocationRecord:
    node_id: str
    kind: str
    subject_id: str
    money_limit: float | None = None
    compute_limit: float | None = None
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)
    schema_version: str = NODE_BUDGET_SCHEMA_VERSION

    @property
    def key(self) -> str:
        return f"{self.node_id}:{self.kind}:{self.subject_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "kind": self.kind,
            "subject_id": self.subject_id,
            "money_limit": self.money_limit,
            "compute_limit": self.compute_limit,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class NodeBudgetGrantRecord:
    grant_id: str
    consumer_node_id: str
    service: str
    period_start: str
    period_end: str
    limits: dict[str, Any]
    status: str
    scope_kind: str
    subject_id: str | None = None
    governance_version: str | None = None
    budget_policy_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    issued_at: str = field(default_factory=_utcnow_iso)
    schema_version: str = NODE_BUDGET_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "grant_id": self.grant_id,
            "consumer_node_id": self.consumer_node_id,
            "service": self.service,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "limits": dict(self.limits or {}),
            "status": self.status,
            "scope_kind": self.scope_kind,
            "subject_id": self.subject_id,
            "governance_version": self.governance_version,
            "budget_policy_version": self.budget_policy_version,
            "metadata": dict(self.metadata or {}),
            "issued_at": self.issued_at,
        }


@dataclass
class NodeBudgetUsageReportRecord:
    node_id: str
    service: str
    grant_id: str
    period_start: str
    period_end: str
    used_requests: int = 0
    used_tokens: int = 0
    used_cost_cents: int = 0
    denials: int = 0
    error_counts: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    reported_at: str = field(default_factory=_utcnow_iso)
    schema_version: str = NODE_BUDGET_SCHEMA_VERSION

    @property
    def key(self) -> str:
        return f"{self.node_id}:{self.service}:{self.grant_id}:{self.period_start}:{self.period_end}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "service": self.service,
            "grant_id": self.grant_id,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "used_requests": self.used_requests,
            "used_tokens": self.used_tokens,
            "used_cost_cents": self.used_cost_cents,
            "denials": self.denials,
            "error_counts": dict(self.error_counts or {}),
            "metadata": dict(self.metadata or {}),
            "reported_at": self.reported_at,
        }


class NodeBudgetStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_repo_root() / "data" / "node_budgets.json")
        self._declarations: dict[str, NodeBudgetCapabilityRecord] = {}
        self._configs: dict[str, NodeBudgetConfigRecord] = {}
        self._allocations: dict[str, NodeBudgetAllocationRecord] = {}
        self._usage_reports: dict[str, NodeBudgetUsageReportRecord] = {}
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
        for item in raw.get("declarations") or []:
            if not isinstance(item, dict):
                continue
            node_id = _clean_text(item.get("node_id"))
            if not node_id:
                continue
            self._declarations[node_id] = NodeBudgetCapabilityRecord(
                node_id=node_id,
                currency=_clean_text(item.get("currency")).upper() or "USD",
                compute_unit=_clean_text(item.get("compute_unit"), lower=True) or "cost_units",
                default_period=_clean_text(item.get("default_period"), lower=True) or "monthly",
                supports_money_budget=bool(item.get("supports_money_budget", True)),
                supports_compute_budget=bool(item.get("supports_compute_budget", True)),
                supports_customer_allocations=bool(item.get("supports_customer_allocations", True)),
                supports_provider_allocations=bool(item.get("supports_provider_allocations", False)),
                supported_providers=sorted(
                    {
                        _clean_text(value, lower=True)
                        for value in list(item.get("supported_providers") or [])
                        if _clean_text(value, lower=True)
                    }
                ),
                setup_requirements=sorted(
                    {
                        _clean_text(value, lower=True)
                        for value in list(item.get("setup_requirements") or [])
                        if _clean_text(value, lower=True)
                    }
                ),
                suggested_money_limit=item.get("suggested_money_limit"),
                suggested_compute_limit=item.get("suggested_compute_limit"),
                declared_at=_clean_text(item.get("declared_at")) or _utcnow_iso(),
                updated_at=_clean_text(item.get("updated_at")) or _utcnow_iso(),
                schema_version=_clean_text(item.get("schema_version")) or NODE_BUDGET_SCHEMA_VERSION,
            )
        for item in raw.get("configs") or []:
            if not isinstance(item, dict):
                continue
            node_id = _clean_text(item.get("node_id"))
            if not node_id:
                continue
            self._configs[node_id] = NodeBudgetConfigRecord(
                node_id=node_id,
                currency=_clean_text(item.get("currency")).upper() or "USD",
                compute_unit=_clean_text(item.get("compute_unit"), lower=True) or "cost_units",
                period=_clean_text(item.get("period"), lower=True) or "monthly",
                reset_policy=_clean_text(item.get("reset_policy"), lower=True) or "calendar",
                enforcement_mode=_clean_text(item.get("enforcement_mode"), lower=True) or "hard_stop",
                overcommit_enabled=bool(item.get("overcommit_enabled", False)),
                shared_customer_pool=bool(item.get("shared_customer_pool", False)),
                shared_provider_pool=bool(item.get("shared_provider_pool", False)),
                node_money_limit=item.get("node_money_limit"),
                node_compute_limit=item.get("node_compute_limit"),
                created_at=_clean_text(item.get("created_at")) or _utcnow_iso(),
                updated_at=_clean_text(item.get("updated_at")) or _utcnow_iso(),
                schema_version=_clean_text(item.get("schema_version")) or NODE_BUDGET_SCHEMA_VERSION,
            )
        for item in raw.get("allocations") or []:
            if not isinstance(item, dict):
                continue
            record = NodeBudgetAllocationRecord(
                node_id=_clean_text(item.get("node_id")),
                kind=_clean_text(item.get("kind"), lower=True),
                subject_id=_clean_text(item.get("subject_id"), lower=True),
                money_limit=item.get("money_limit"),
                compute_limit=item.get("compute_limit"),
                created_at=_clean_text(item.get("created_at")) or _utcnow_iso(),
                updated_at=_clean_text(item.get("updated_at")) or _utcnow_iso(),
                schema_version=_clean_text(item.get("schema_version")) or NODE_BUDGET_SCHEMA_VERSION,
            )
            if record.node_id and record.kind in ALLOCATION_KINDS and record.subject_id:
                self._allocations[record.key] = record
        for item in raw.get("usage_reports") or []:
            if not isinstance(item, dict):
                continue
            node_id = _clean_text(item.get("node_id"))
            service = _clean_text(item.get("service"))
            grant_id = _clean_text(item.get("grant_id"))
            period_start = _clean_text(item.get("period_start"))
            period_end = _clean_text(item.get("period_end"))
            if not (node_id and service and grant_id and period_start and period_end):
                continue
            error_counts = item.get("error_counts") if isinstance(item.get("error_counts"), dict) else {}
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            record = NodeBudgetUsageReportRecord(
                node_id=node_id,
                service=service,
                grant_id=grant_id,
                period_start=period_start,
                period_end=period_end,
                used_requests=int(item.get("used_requests") or 0),
                used_tokens=int(item.get("used_tokens") or 0),
                used_cost_cents=int(item.get("used_cost_cents") or 0),
                denials=int(item.get("denials") or 0),
                error_counts={str(k): int(v or 0) for k, v in error_counts.items() if str(k or "").strip()},
                metadata=dict(metadata),
                reported_at=_clean_text(item.get("reported_at")) or _utcnow_iso(),
                schema_version=_clean_text(item.get("schema_version")) or NODE_BUDGET_SCHEMA_VERSION,
            )
            self._usage_reports[record.key] = record

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": NODE_BUDGET_SCHEMA_VERSION,
            "declarations": [item.to_dict() for item in sorted(self._declarations.values(), key=lambda value: value.node_id)],
            "configs": [item.to_dict() for item in sorted(self._configs.values(), key=lambda value: value.node_id)],
            "allocations": [
                item.to_dict()
                for item in sorted(self._allocations.values(), key=lambda value: (value.node_id, value.kind, value.subject_id))
            ],
            "usage_reports": [
                item.to_dict()
                for item in sorted(
                    self._usage_reports.values(),
                    key=lambda value: (value.node_id, value.service, value.period_start, value.grant_id),
                )
            ],
        }
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def get_declaration(self, node_id: str) -> NodeBudgetCapabilityRecord | None:
        return self._declarations.get(_clean_text(node_id))

    def upsert_declaration(self, record: NodeBudgetCapabilityRecord) -> NodeBudgetCapabilityRecord:
        existing = self._declarations.get(record.node_id)
        if existing is not None:
            record.declared_at = existing.declared_at
        record.updated_at = _utcnow_iso()
        self._declarations[record.node_id] = record
        self._save()
        return record

    def get_config(self, node_id: str) -> NodeBudgetConfigRecord | None:
        return self._configs.get(_clean_text(node_id))

    def upsert_config(self, record: NodeBudgetConfigRecord) -> NodeBudgetConfigRecord:
        existing = self._configs.get(record.node_id)
        if existing is not None:
            record.created_at = existing.created_at
        record.updated_at = _utcnow_iso()
        self._configs[record.node_id] = record
        self._save()
        return record

    def delete_config(self, node_id: str) -> NodeBudgetConfigRecord | None:
        removed = self._configs.pop(_clean_text(node_id), None)
        if removed is not None:
            self._save()
        return removed

    def clear_usage_reports(self, node_id: str) -> int:
        node_key = _clean_text(node_id)
        before = len(self._usage_reports)
        self._usage_reports = {key: value for key, value in self._usage_reports.items() if value.node_id != node_key}
        removed = before - len(self._usage_reports)
        if removed:
            self._save()
        return removed

    def replace_allocations(self, node_id: str, kind: str, allocations: list[NodeBudgetAllocationRecord]) -> list[NodeBudgetAllocationRecord]:
        node_key = _clean_text(node_id)
        kind_key = _clean_text(kind, lower=True)
        self._allocations = {
            key: value for key, value in self._allocations.items() if not (value.node_id == node_key and value.kind == kind_key)
        }
        for record in allocations:
            self._allocations[record.key] = record
        self._save()
        return self.list_allocations(node_key, kind=kind_key)

    def list_allocations(self, node_id: str | None = None, *, kind: str | None = None) -> list[NodeBudgetAllocationRecord]:
        node_key = _clean_text(node_id)
        kind_key = _clean_text(kind, lower=True)
        items = []
        for item in sorted(self._allocations.values(), key=lambda value: (value.node_id, value.kind, value.subject_id)):
            if node_key and item.node_id != node_key:
                continue
            if kind_key and item.kind != kind_key:
                continue
            items.append(item)
        return items

    def remove_all_allocations(self, node_id: str, *, kind: str | None = None) -> int:
        node_key = _clean_text(node_id)
        kind_key = _clean_text(kind, lower=True)
        before = len(self._allocations)
        self._allocations = {
            key: value
            for key, value in self._allocations.items()
            if not (value.node_id == node_key and (not kind_key or value.kind == kind_key))
        }
        removed = before - len(self._allocations)
        if removed:
            self._save()
        return removed

    def upsert_allocation(self, record: NodeBudgetAllocationRecord) -> NodeBudgetAllocationRecord:
        existing = self._allocations.get(record.key)
        if existing is not None:
            record.created_at = existing.created_at
        record.updated_at = _utcnow_iso()
        self._allocations[record.key] = record
        self._save()
        return record

    def delete_allocation(self, node_id: str, kind: str, subject_id: str) -> NodeBudgetAllocationRecord | None:
        key = f"{_clean_text(node_id)}:{_clean_text(kind, lower=True)}:{_clean_text(subject_id, lower=True)}"
        removed = self._allocations.pop(key, None)
        if removed is not None:
            self._save()
        return removed

    def upsert_usage_report(self, record: NodeBudgetUsageReportRecord) -> NodeBudgetUsageReportRecord:
        record.reported_at = _utcnow_iso()
        self._usage_reports[record.key] = record
        self._save()
        return record

    def list_usage_reports(self, node_id: str | None = None, *, grant_id: str | None = None) -> list[NodeBudgetUsageReportRecord]:
        node_key = _clean_text(node_id)
        grant_key = _clean_text(grant_id)
        items = []
        for item in sorted(
            self._usage_reports.values(),
            key=lambda value: (value.node_id, value.service, value.period_start, value.grant_id),
        ):
            if node_key and item.node_id != node_key:
                continue
            if grant_key and item.grant_id != grant_key:
                continue
            items.append(item)
        return items

    def list_bundles(self) -> list[dict[str, Any]]:
        node_ids = sorted(
            set(self._declarations.keys())
            | set(self._configs.keys())
            | {item.node_id for item in self._allocations.values()}
            | {item.node_id for item in self._usage_reports.values()}
        )
        return [self.bundle(node_id) for node_id in node_ids]

    def bundle(self, node_id: str) -> dict[str, Any]:
        declaration = self.get_declaration(node_id)
        config = self.get_config(node_id)
        customers = [item.to_dict() for item in self.list_allocations(node_id, kind="customer")]
        providers = [item.to_dict() for item in self.list_allocations(node_id, kind="provider")]
        setup_status = "not_declared"
        if declaration is not None:
            setup_status = "configured" if config is not None else "needs_configuration"
        return {
            "node_id": _clean_text(node_id),
            "setup_status": setup_status,
            "declaration": declaration.to_dict() if declaration is not None else None,
            "node_budget": config.to_dict() if config is not None else None,
            "customer_allocations": customers,
            "provider_allocations": providers,
        }


class NodeBudgetService:
    def __init__(self, store: NodeBudgetStore, model_routing_registry: ModelRoutingRegistryService | None = None) -> None:
        self._store = store
        self._model_routing_registry = model_routing_registry

    def declare_budget_capabilities(self, *, node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        node_key = _clean_text(node_id)
        if not node_key:
            raise ValueError("node_id_required")
        compute_unit = _clean_text(payload.get("compute_unit"), lower=True) or "cost_units"
        if compute_unit not in SUPPORTED_COMPUTE_UNITS:
            raise ValueError("unsupported_compute_unit")
        default_period = _clean_text(payload.get("default_period"), lower=True) or "monthly"
        if default_period not in SUPPORTED_PERIODS:
            raise ValueError("unsupported_budget_period")
        declaration = NodeBudgetCapabilityRecord(
            node_id=node_key,
            currency=_clean_text(payload.get("currency")).upper() or "USD",
            compute_unit=compute_unit,
            default_period=default_period,
            supports_money_budget=bool(payload.get("supports_money_budget", True)),
            supports_compute_budget=bool(payload.get("supports_compute_budget", True)),
            supports_customer_allocations=bool(payload.get("supports_customer_allocations", True)),
            supports_provider_allocations=bool(payload.get("supports_provider_allocations", False)),
            supported_providers=sorted(
                {
                    _clean_text(value, lower=True)
                    for value in list(payload.get("supported_providers") or [])
                    if _clean_text(value, lower=True)
                }
            ),
            setup_requirements=sorted(
                {
                    _clean_text(value, lower=True)
                    for value in list(payload.get("setup_requirements") or [])
                    if _clean_text(value, lower=True)
                }
            ),
            suggested_money_limit=_coerce_optional_float(payload.get("suggested_money_limit")),
            suggested_compute_limit=_coerce_optional_float(payload.get("suggested_compute_limit")),
        )
        return self._store.upsert_declaration(declaration).to_dict()

    def configure_node_budget(
        self,
        *,
        node_id: str,
        node_budget: dict[str, Any],
        customer_allocations: list[dict[str, Any]] | None = None,
        provider_allocations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        node_key = _clean_text(node_id)
        if not node_key:
            raise ValueError("node_id_required")
        declaration = self._store.get_declaration(node_key)
        if declaration is None:
            raise ValueError("budget_capabilities_not_declared")

        currency = _clean_text(node_budget.get("currency")).upper() or declaration.currency or "USD"
        compute_unit = _clean_text(node_budget.get("compute_unit"), lower=True) or declaration.compute_unit
        if compute_unit not in SUPPORTED_COMPUTE_UNITS:
            raise ValueError("unsupported_compute_unit")
        period = _clean_text(node_budget.get("period"), lower=True) or declaration.default_period
        if period not in SUPPORTED_PERIODS:
            raise ValueError("unsupported_budget_period")
        reset_policy = _clean_text(node_budget.get("reset_policy"), lower=True) or "calendar"
        if reset_policy not in SUPPORTED_RESET_POLICIES:
            raise ValueError("unsupported_reset_policy")
        enforcement_mode = _clean_text(node_budget.get("enforcement_mode"), lower=True) or "hard_stop"
        if enforcement_mode not in SUPPORTED_ENFORCEMENT_MODES:
            raise ValueError("unsupported_enforcement_mode")

        money_limit = _coerce_optional_float(node_budget.get("node_money_limit"))
        compute_limit = _coerce_optional_float(node_budget.get("node_compute_limit"))
        if money_limit is not None and not declaration.supports_money_budget:
            raise ValueError("money_budget_not_supported")
        if compute_limit is not None and not declaration.supports_compute_budget:
            raise ValueError("compute_budget_not_supported")

        config = NodeBudgetConfigRecord(
            node_id=node_key,
            currency=currency,
            compute_unit=compute_unit,
            period=period,
            reset_policy=reset_policy,
            enforcement_mode=enforcement_mode,
            overcommit_enabled=bool(node_budget.get("overcommit_enabled", False)),
            shared_customer_pool=bool(node_budget.get("shared_customer_pool", False)),
            shared_provider_pool=bool(node_budget.get("shared_provider_pool", False)),
            node_money_limit=money_limit,
            node_compute_limit=compute_limit,
        )
        config = self._store.upsert_config(config)

        customer_records = self._normalize_allocations(
            node_id=node_key,
            kind="customer",
            allocations=customer_allocations or [],
            declaration=declaration,
        )
        provider_records = self._normalize_allocations(
            node_id=node_key,
            kind="provider",
            allocations=provider_allocations or [],
            declaration=declaration,
        )

        self._validate_allocation_totals(config=config, customer_records=customer_records, provider_records=provider_records)
        self._store.replace_allocations(node_key, "customer", customer_records)
        self._store.replace_allocations(node_key, "provider", provider_records)
        return self._store.bundle(node_key)

    def list_bundles(self) -> list[dict[str, Any]]:
        return [self.get_bundle(item["node_id"]) for item in self._store.list_bundles()]

    def get_bundle(self, node_id: str) -> dict[str, Any]:
        bundle = self._store.bundle(node_id)
        if not bundle.get("declaration") and not bundle.get("node_budget"):
            raise ValueError("node_budget_not_found")
        bundle["budget_policy"] = self.budget_policy(node_id)
        if bundle.get("node_budget"):
            bundle["usage_summary"] = self.usage_summary(node_id)
            bundle["usage_reports"] = self.list_usage_reports(node_id=node_id)
        return bundle

    def budget_policy(self, node_id: str, *, governance_version: str | None = None) -> dict[str, Any]:
        node_key = _clean_text(node_id)
        declaration = self._store.get_declaration(node_key)
        config = self._store.get_config(node_key)
        if declaration is None and config is None:
            raise ValueError("node_budget_not_found")
        if config is None:
            return {
                "node_id": node_key,
                "service": NODE_BUDGET_SERVICE_ID,
                "status": "not_configured",
                "budget_policy_version": None,
                "governance_version": governance_version,
                "grants": [],
                "fallback_rules": {
                    "distribution_mode": "push_first_poll_second",
                    "allow_cached_grants_until_expiry": True,
                    "queue_usage_reports_while_core_unavailable": True,
                    "degrade_when_cached_grants_expire": True,
                },
            }

        period_start, period_end = self._current_period_window(config)
        version = self._budget_policy_version(node_key)
        return {
            "node_id": node_key,
            "service": NODE_BUDGET_SERVICE_ID,
            "status": "active",
            "budget_policy_version": version,
            "governance_version": governance_version,
            "period_start": period_start,
            "period_end": period_end,
            "issued_at": config.updated_at,
            "enforcement_mode": config.enforcement_mode,
            "shared_customer_pool": bool(config.shared_customer_pool),
            "shared_provider_pool": bool(config.shared_provider_pool),
            "overcommit_enabled": bool(config.overcommit_enabled),
            "allowed_providers": list((declaration.supported_providers if declaration is not None else []) or []),
            "fallback_rules": {
                "distribution_mode": "push_first_poll_second",
                "allow_cached_grants_until_expiry": True,
                "queue_usage_reports_while_core_unavailable": True,
                "degrade_when_cached_grants_expire": True,
                "reconcile_poll_interval_s": 60,
            },
            "grants": self.derive_grants(node_key, governance_version=governance_version),
        }

    def derive_grants(self, node_id: str, *, governance_version: str | None = None) -> list[dict[str, Any]]:
        node_key = _clean_text(node_id)
        config = self._store.get_config(node_key)
        if config is None:
            return []
        period_start, period_end = self._current_period_window(config)
        policy_version = self._budget_policy_version(node_key)

        grants: list[NodeBudgetGrantRecord] = [
            self._grant_record(
                node_id=node_key,
                scope_kind="node",
                subject_id=None,
                money_limit=config.node_money_limit,
                compute_limit=config.node_compute_limit,
                compute_unit=config.compute_unit,
                enforcement_mode=config.enforcement_mode,
                period_start=period_start,
                period_end=period_end,
                governance_version=governance_version,
                policy_version=policy_version,
            )
        ]
        for item in self._store.list_allocations(node_key, kind="customer"):
            grants.append(
                self._grant_record(
                    node_id=node_key,
                    scope_kind="customer",
                    subject_id=item.subject_id,
                    money_limit=item.money_limit,
                    compute_limit=item.compute_limit,
                    compute_unit=config.compute_unit,
                    enforcement_mode=config.enforcement_mode,
                    period_start=period_start,
                    period_end=period_end,
                    governance_version=governance_version,
                    policy_version=policy_version,
                )
            )
        for item in self._store.list_allocations(node_key, kind="provider"):
            grants.append(
                self._grant_record(
                    node_id=node_key,
                    scope_kind="provider",
                    subject_id=item.subject_id,
                    money_limit=item.money_limit,
                    compute_limit=item.compute_limit,
                    compute_unit=config.compute_unit,
                    enforcement_mode=config.enforcement_mode,
                    period_start=period_start,
                    period_end=period_end,
                    governance_version=governance_version,
                    policy_version=policy_version,
                )
            )
        return [item.to_dict() for item in grants]

    def list_usage_reports(self, *, node_id: str, grant_id: str | None = None) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._store.list_usage_reports(node_id=node_id, grant_id=grant_id)]

    def effective_budget_view(
        self,
        *,
        node_id: str,
        task_family: str,
        provider: str | None = None,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        node_key = _clean_text(node_id)
        config = self._store.get_config(node_key)
        task_family_key = _clean_text(task_family, lower=True)
        provider_key = _clean_text(provider, lower=True)
        model_key = _clean_text(model_id, lower=True)
        if config is None:
            return {
                "status": "not_configured",
                "budget_node_id": node_key,
                "service": NODE_BUDGET_SERVICE_ID,
                "provider": provider_key or None,
                "task_family": task_family_key,
                "model_id": model_key or None,
                "admissible": False,
                "reason": "node_budget_not_configured",
            }

        grants = self.derive_grants(node_key)
        provider_allocations = {item.subject_id for item in self._store.list_allocations(node_key, kind="provider")}
        selected_grant: dict[str, Any] | None = None
        if provider_key:
            selected_grant = next(
                (
                    grant
                    for grant in grants
                    if str(grant.get("scope_kind") or "") == "provider"
                    and _clean_text(grant.get("subject_id"), lower=True) == provider_key
                ),
                None,
            )
            if selected_grant is None and provider_allocations and not bool(config.shared_provider_pool):
                return {
                    "status": "no_matching_grant",
                    "budget_node_id": node_key,
                    "service": NODE_BUDGET_SERVICE_ID,
                    "provider": provider_key,
                    "task_family": task_family_key,
                    "model_id": model_key or None,
                    "admissible": False,
                    "reason": "provider_budget_allocation_required",
                }
        if selected_grant is None:
            selected_grant = next((grant for grant in grants if str(grant.get("scope_kind") or "") == "node"), None)
        if selected_grant is None:
            return {
                "status": "no_matching_grant",
                "budget_node_id": node_key,
                "service": NODE_BUDGET_SERVICE_ID,
                "provider": provider_key or None,
                "task_family": task_family_key,
                "model_id": model_key or None,
                "admissible": False,
                "reason": "grant_not_found",
            }

        limits = dict(selected_grant.get("limits") or {})
        usage_reports = self._store.list_usage_reports(node_id=node_key, grant_id=str(selected_grant.get("grant_id") or ""))
        consumed_requests = sum(int(item.used_requests or 0) for item in usage_reports)
        consumed_tokens = sum(int(item.used_tokens or 0) for item in usage_reports)
        consumed_cost_cents = sum(int(item.used_cost_cents or 0) for item in usage_reports)
        remaining: dict[str, Any] = {}
        if limits.get("max_requests") is not None:
            remaining["max_requests"] = max(0, int(limits.get("max_requests") or 0) - consumed_requests)
        if limits.get("max_tokens") is not None:
            remaining["max_tokens"] = max(0, int(limits.get("max_tokens") or 0) - consumed_tokens)
        if limits.get("max_cost_cents") is not None:
            remaining["max_cost_cents"] = max(0, int(limits.get("max_cost_cents") or 0) - consumed_cost_cents)
        raw_status = str(selected_grant.get("status") or "active")
        admissible = raw_status == "active" and (not remaining or all(int(value) > 0 for value in remaining.values()))
        return {
            "status": "active" if admissible else (raw_status if raw_status != "active" else "exhausted"),
            "budget_node_id": node_key,
            "enforcement_mode": config.enforcement_mode,
            "grant_id": selected_grant.get("grant_id"),
            "service": NODE_BUDGET_SERVICE_ID,
            "provider": provider_key or None,
            "task_family": task_family_key,
            "model_id": model_key or None,
            "grant_scope_kind": selected_grant.get("scope_kind"),
            "period_start": selected_grant.get("period_start"),
            "period_end": selected_grant.get("period_end"),
            "limits": limits,
            "consumed": {
                "used_requests": consumed_requests,
                "used_tokens": consumed_tokens,
                "used_cost_cents": consumed_cost_cents,
            },
            "remaining": remaining,
            "admissible": admissible,
            "reason": None if admissible else ("budget_exhausted" if raw_status == "active" else raw_status),
        }

    def grant_owner_node_id(self, grant_id: str | None) -> str | None:
        grant_key = _clean_text(grant_id)
        if not grant_key.startswith("grant:"):
            return None
        parts = grant_key.split(":")
        if len(parts) < 3:
            return None
        node_key = _clean_text(parts[1])
        return node_key or None

    def report_usage_summary(self, *, node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        service = _clean_text(payload.get("service")) or NODE_BUDGET_SERVICE_ID
        grant_id = _clean_text(payload.get("grant_id"))
        if not grant_id:
            raise ValueError("grant_id_required")
        reporter_node_key = _clean_text(node_id)
        owner_node_key = self.grant_owner_node_id(grant_id) or reporter_node_key
        config = self._store.get_config(owner_node_key)
        if config is None:
            raise ValueError("node_budget_not_configured")
        period_start = _clean_text(payload.get("period_start"))
        period_end = _clean_text(payload.get("period_end"))
        if not period_start or not period_end:
            start, end = self._current_period_window(config)
            period_start = period_start or start
            period_end = period_end or end
        error_counts = payload.get("error_counts") if isinstance(payload.get("error_counts"), dict) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        provider = _clean_text(payload.get("provider"), lower=True)
        task_family = _clean_text(payload.get("task_family"), lower=True)
        model_id = _clean_text(payload.get("model_id"), lower=True)
        if provider:
            metadata["provider"] = provider
        if task_family:
            metadata["task_family"] = task_family
        if model_id:
            metadata["model_id"] = model_id
        if reporter_node_key and reporter_node_key != owner_node_key:
            metadata["reported_by_node_id"] = reporter_node_key
        record = NodeBudgetUsageReportRecord(
            node_id=owner_node_key,
            service=service,
            grant_id=grant_id,
            period_start=period_start,
            period_end=period_end,
            used_requests=max(0, int(payload.get("used_requests") or 0)),
            used_tokens=max(0, int(payload.get("used_tokens") or 0)),
            used_cost_cents=max(0, int(payload.get("used_cost_cents") or 0)),
            denials=max(0, int(payload.get("denials") or 0)),
            error_counts={str(k): max(0, int(v or 0)) for k, v in error_counts.items() if str(k or "").strip()},
            metadata=dict(metadata),
        )
        return self._store.upsert_usage_report(record).to_dict()

    def delete_node_budget(self, node_id: str) -> dict[str, Any]:
        node_key = _clean_text(node_id)
        config = self._store.delete_config(node_key)
        self._store.remove_all_allocations(node_key)
        if config is None:
            raise ValueError("node_budget_not_found")
        return self.get_bundle(node_key)

    def list_allocations(self, *, node_id: str, kind: str) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._store.list_allocations(node_id, kind=kind)]

    def upsert_allocation(self, *, node_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        node_key = _clean_text(node_id)
        kind_key = _clean_text(kind, lower=True)
        declaration = self._store.get_declaration(node_key)
        config = self._store.get_config(node_key)
        if declaration is None or config is None:
            raise ValueError("node_budget_not_found")

        subject_id = _clean_text(payload.get("subject_id"), lower=True)
        if not subject_id:
            raise ValueError("subject_id_required")
        normalized = self._normalize_allocations(node_id=node_key, kind=kind_key, allocations=[payload], declaration=declaration)
        if not normalized:
            raise ValueError("subject_id_required")
        record = normalized[0]
        existing = [item for item in self._store.list_allocations(node_key, kind=kind_key) if item.subject_id != subject_id]
        merged = existing + [record]
        customer_records = merged if kind_key == "customer" else self._store.list_allocations(node_key, kind="customer")
        provider_records = merged if kind_key == "provider" else self._store.list_allocations(node_key, kind="provider")
        self._validate_allocation_totals(config=config, customer_records=customer_records, provider_records=provider_records)
        return self._store.upsert_allocation(record).to_dict()

    def delete_allocation(self, *, node_id: str, kind: str, subject_id: str) -> dict[str, Any]:
        removed = self._store.delete_allocation(node_id, kind, subject_id)
        if removed is None:
            raise ValueError("budget_allocation_not_found")
        return removed.to_dict()

    def usage_summary(self, node_id: str) -> dict[str, Any]:
        node_key = _clean_text(node_id)
        config = self._store.get_config(node_key)
        if config is None:
            raise ValueError("node_budget_not_found")

        reports = self._store.list_usage_reports(node_id=node_key)
        customer_allocations = self._store.list_allocations(node_key, kind="customer")
        provider_allocations = self._store.list_allocations(node_key, kind="provider")

        summary = {
            "node": self._scope_usage_summary(
                money_limit=config.node_money_limit,
                compute_limit=config.node_compute_limit,
                compute_unit=config.compute_unit,
                reports=reports,
                scope_kind="node",
            ),
            "customers": [],
            "providers": [],
            "alerts": [],
        }

        for item in customer_allocations:
            scope_summary = self._scope_usage_summary(
                money_limit=item.money_limit,
                compute_limit=item.compute_limit,
                compute_unit=config.compute_unit,
                reports=[
                    report
                    for report in reports
                    if _clean_text(report.metadata.get("customer_id") or report.metadata.get("customer"), lower=True) == item.subject_id
                ],
                scope_kind="customer",
                subject_id=item.subject_id,
            )
            summary["customers"].append(scope_summary)

        for item in provider_allocations:
            scope_summary = self._scope_usage_summary(
                money_limit=item.money_limit,
                compute_limit=item.compute_limit,
                compute_unit=config.compute_unit,
                reports=[
                    report
                    for report in reports
                    if _clean_text(report.metadata.get("provider_id") or report.metadata.get("provider"), lower=True) == item.subject_id
                ],
                scope_kind="provider",
                subject_id=item.subject_id,
            )
            summary["providers"].append(scope_summary)

        summary["alerts"] = list(summary["node"].get("alerts") or [])
        for group in ("customers", "providers"):
            for item in summary[group]:
                summary["alerts"].extend(list(item.get("alerts") or []))
        return summary

    def usage_inspection(self, node_id: str) -> dict[str, Any]:
        node_key = _clean_text(node_id)
        config = self._store.get_config(node_key)
        if config is None:
            raise ValueError("node_budget_not_found")
        return {
            "node_id": node_key,
            "usage_summary": self.usage_summary(node_key),
            "usage_reports": [item.to_dict() for item in self._store.list_usage_reports(node_id=node_key)],
            "usage_report_rollups": self.usage_report_rollups(node_key),
            "budget_policy": self.budget_policy(node_key),
            "next_reset_at": self._next_reset_at(config),
            "period": config.period,
            "reset_policy": config.reset_policy,
        }

    def usage_report_rollups(self, node_id: str) -> dict[str, list[dict[str, Any]]]:
        node_key = _clean_text(node_id)
        reports = self._store.list_usage_reports(node_id=node_key)
        by_service: dict[str, dict[str, Any]] = {}
        by_provider: dict[str, dict[str, Any]] = {}
        by_task_family: dict[str, dict[str, Any]] = {}

        def _accumulate(bucket: dict[str, dict[str, Any]], key: str, *, field_name: str, report: NodeBudgetUsageReportRecord) -> None:
            row = bucket.setdefault(
                key,
                {
                    field_name: key,
                    "used_requests": 0,
                    "used_tokens": 0,
                    "used_cost_cents": 0,
                    "denials": 0,
                },
            )
            row["used_requests"] += int(report.used_requests or 0)
            row["used_tokens"] += int(report.used_tokens or 0)
            row["used_cost_cents"] += int(report.used_cost_cents or 0)
            row["denials"] += int(report.denials or 0)

        for report in reports:
            _accumulate(by_service, report.service, field_name="service", report=report)
            provider = _clean_text(report.metadata.get("provider"), lower=True)
            if provider:
                _accumulate(by_provider, provider, field_name="provider", report=report)
            task_family = _clean_text(report.metadata.get("task_family"), lower=True)
            if task_family:
                _accumulate(by_task_family, task_family, field_name="task_family", report=report)
        return {
            "services": list(by_service.values()),
            "providers": list(by_provider.values()),
            "task_families": list(by_task_family.values()),
        }

    def export_usage_rows(self, *, node_id: str | None = None) -> list[dict[str, Any]]:
        target_nodes = [node_id] if _clean_text(node_id) else [item["node_id"] for item in self._store.list_bundles()]
        rows: list[dict[str, Any]] = []
        for raw_node_id in target_nodes:
            node_key = _clean_text(raw_node_id)
            if not node_key:
                continue
            try:
                inspection = self.usage_inspection(node_key)
            except ValueError:
                continue
            rows.extend(self._usage_rows_for_scope(node_key, inspection["usage_summary"].get("node"), inspection))
            for scope in inspection["usage_summary"].get("customers") or []:
                rows.extend(self._usage_rows_for_scope(node_key, scope, inspection))
            for scope in inspection["usage_summary"].get("providers") or []:
                rows.extend(self._usage_rows_for_scope(node_key, scope, inspection))
        return rows

    def _usage_rows_for_scope(self, node_id: str, scope: dict[str, Any] | None, inspection: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(scope, dict):
            return []
        alerts = scope.get("alerts") or []
        rows = [
            {
                "node_id": node_id,
                "scope_kind": scope.get("scope_kind"),
                "subject_id": scope.get("subject_id"),
                "period": inspection.get("period"),
                "reset_policy": inspection.get("reset_policy"),
                "next_reset_at": inspection.get("next_reset_at"),
                "money_limit": scope.get("money_limit"),
                "compute_limit": scope.get("compute_limit"),
                "reserved_money": scope.get("reserved_money"),
                "reserved_compute": scope.get("reserved_compute"),
                "actual_money": scope.get("actual_money"),
                "actual_compute": scope.get("actual_compute"),
                "remaining_money": scope.get("remaining_money"),
                "remaining_compute": scope.get("remaining_compute"),
                "money_utilization": scope.get("money_utilization"),
                "compute_utilization": scope.get("compute_utilization"),
                "alert_count": len(alerts),
                "alerts": alerts,
            }
        ]
        return rows

    def top_up_budget(
        self,
        *,
        node_id: str,
        money_delta: float | None = None,
        compute_delta: float | None = None,
    ) -> dict[str, Any]:
        node_key = _clean_text(node_id)
        config = self._store.get_config(node_key)
        if config is None:
            raise ValueError("node_budget_not_found")
        money_bump = _coerce_optional_float(money_delta)
        compute_bump = _coerce_optional_float(compute_delta)
        if money_bump is None and compute_bump is None:
            raise ValueError("budget_top_up_required")
        if money_bump is not None:
            config.node_money_limit = round(float(config.node_money_limit or 0.0) + money_bump, 6)
        if compute_bump is not None:
            config.node_compute_limit = round(float(config.node_compute_limit or 0.0) + compute_bump, 6)
        self._store.upsert_config(config)
        return self.get_bundle(node_key)

    def reset_budget_usage(self, *, node_id: str) -> dict[str, Any]:
        node_key = _clean_text(node_id)
        config = self._store.get_config(node_key)
        if config is None:
            raise ValueError("node_budget_not_found")
        self._store.clear_usage_reports(node_key)
        config.updated_at = _utcnow_iso()
        self._store.upsert_config(config)
        return self.get_bundle(node_key)

    def set_temporary_override(
        self,
        *,
        node_id: str,
        enforcement_mode: str | None = None,
        overcommit_enabled: bool | None = None,
    ) -> dict[str, Any]:
        node_key = _clean_text(node_id)
        config = self._store.get_config(node_key)
        if config is None:
            raise ValueError("node_budget_not_found")
        updated = False
        if enforcement_mode is not None:
            mode = _clean_text(enforcement_mode, lower=True)
            if mode not in SUPPORTED_ENFORCEMENT_MODES:
                raise ValueError("unsupported_enforcement_mode")
            config.enforcement_mode = mode
            updated = True
        if overcommit_enabled is not None:
            config.overcommit_enabled = bool(overcommit_enabled)
            updated = True
        if not updated:
            raise ValueError("budget_override_required")
        self._store.upsert_config(config)
        return self.get_bundle(node_key)

    def budget_grant_topics(self, node_id: str) -> list[str]:
        node_key = _clean_text(node_id)
        if not node_key:
            return []
        return [f"hexe/policy/grants/{node_key}"]

    def budget_revocation_topics(self, *, node_id: str, grant_id: str | None = None) -> list[str]:
        node_key = _clean_text(node_id)
        topics = [f"hexe/policy/revocations/{node_key}"] if node_key else []
        grant_key = _clean_text(grant_id)
        if grant_key:
            topics.append(f"hexe/policy/revocations/{grant_key}")
        return topics

    def budget_revocation_payloads(self, node_id: str, *, reason: str) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for grant in self.derive_grants(node_id):
            payload = {
                "id": f"budget-revocation:{_clean_text(node_id)}:{_clean_text(grant.get('grant_id'))}",
                "node_id": _clean_text(node_id),
                "grant_id": grant.get("grant_id"),
                "service": grant.get("service") or NODE_BUDGET_SERVICE_ID,
                "reason": _clean_text(reason) or "budget_policy_removed",
                "status": "revoked",
            }
            payloads.append(payload)
        if not payloads:
            payloads.append(
                {
                    "id": f"budget-revocation:{_clean_text(node_id)}",
                    "node_id": _clean_text(node_id),
                    "grant_id": None,
                    "service": NODE_BUDGET_SERVICE_ID,
                    "reason": _clean_text(reason) or "budget_policy_removed",
                    "status": "revoked",
                }
            )
        return payloads

    def _budget_policy_version(self, node_id: str) -> str:
        bundle = self._store.bundle(node_id)
        digest = hashlib.sha256(json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return f"nbp-{digest[:12]}"

    def _current_period_window(self, config: NodeBudgetConfigRecord) -> tuple[str, str]:
        now = datetime.now(timezone.utc)
        if config.period == "daily":
            start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
            end = start + timedelta(days=1)
            return start.isoformat(), end.isoformat()
        if config.period == "monthly":
            start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
            year = now.year + (1 if now.month == 12 else 0)
            month = 1 if now.month == 12 else now.month + 1
            end = datetime(year, month, 1, tzinfo=timezone.utc)
            return start.isoformat(), end.isoformat()
        if config.reset_policy == "rolling":
            delta = timedelta(days=1 if config.period == "daily" else 30)
            try:
                start = datetime.fromisoformat(config.updated_at)
            except Exception:
                start = now
            end = start + delta
            return start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()
        try:
            start = datetime.fromisoformat(config.updated_at)
        except Exception:
            start = now
        end = start + timedelta(days=365)
        return start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()

    def _grant_limits(self, *, compute_unit: str, money_limit: float | None, compute_limit: float | None) -> tuple[dict[str, Any], dict[str, Any]]:
        limits: dict[str, Any] = {}
        metadata: dict[str, Any] = {}
        if money_limit is not None:
            limits["max_cost_cents"] = max(0, int(round(float(money_limit) * 100)))
        if compute_limit is not None:
            if compute_unit == "tokens":
                limits["max_tokens"] = max(0, int(round(float(compute_limit))))
            elif compute_unit == "requests":
                limits["max_requests"] = max(0, int(round(float(compute_limit))))
            else:
                metadata["compute_unit"] = compute_unit
                metadata["max_compute_units"] = round(float(compute_limit), 6)
        return limits, metadata

    def _grant_record(
        self,
        *,
        node_id: str,
        scope_kind: str,
        subject_id: str | None,
        money_limit: float | None,
        compute_limit: float | None,
        compute_unit: str,
        enforcement_mode: str,
        period_start: str,
        period_end: str,
        governance_version: str | None,
        policy_version: str,
    ) -> NodeBudgetGrantRecord:
        limits, metadata = self._grant_limits(compute_unit=compute_unit, money_limit=money_limit, compute_limit=compute_limit)
        metadata.update({"scope_kind": scope_kind, "enforcement_mode": enforcement_mode})
        metadata["service"] = NODE_BUDGET_SERVICE_ID
        if subject_id:
            metadata["subject_id"] = subject_id
        if scope_kind == "provider" and subject_id:
            metadata["provider"] = subject_id
        grant_suffix = scope_kind if not subject_id else f"{scope_kind}:{subject_id}"
        status = "expired" if datetime.fromisoformat(period_end) <= datetime.now(timezone.utc) else "active"
        return NodeBudgetGrantRecord(
            grant_id=f"grant:{node_id}:{grant_suffix}",
            consumer_node_id=node_id,
            service=NODE_BUDGET_SERVICE_ID,
            period_start=period_start,
            period_end=period_end,
            limits=limits,
            status=status,
            scope_kind=scope_kind,
            subject_id=subject_id,
            governance_version=governance_version,
            budget_policy_version=policy_version,
            metadata=metadata,
            issued_at=period_start,
        )

    def _scope_usage_summary(
        self,
        *,
        money_limit: float | None,
        compute_limit: float | None,
        compute_unit: str,
        reports: list[NodeBudgetUsageReportRecord],
        scope_kind: str,
        subject_id: str | None = None,
    ) -> dict[str, Any]:
        reserved_money = 0.0
        reserved_compute = 0.0
        actual_money = round(sum(float(item.used_cost_cents or 0) for item in reports) / 100.0, 6)
        if compute_unit == "tokens":
            actual_compute = round(sum(float(item.used_tokens or 0) for item in reports), 6)
        elif compute_unit == "requests":
            actual_compute = round(sum(float(item.used_requests or 0) for item in reports), 6)
        else:
            actual_compute = 0.0
        remaining_money = None if money_limit is None else round(float(money_limit) - reserved_money - actual_money, 6)
        remaining_compute = None if compute_limit is None else round(float(compute_limit) - reserved_compute - actual_compute, 6)
        summary = {
            "scope_kind": scope_kind,
            "subject_id": subject_id,
            "money_limit": money_limit,
            "compute_limit": compute_limit,
            "reserved_money": reserved_money,
            "reserved_compute": reserved_compute,
            "actual_money": actual_money,
            "actual_compute": actual_compute,
            "remaining_money": remaining_money,
            "remaining_compute": remaining_compute,
            "alerts": [],
        }
        money_used = reserved_money + actual_money
        compute_used = reserved_compute + actual_compute
        summary["money_utilization"] = None if money_limit in {None, 0} else round(money_used / float(money_limit), 6)
        summary["compute_utilization"] = None if compute_limit in {None, 0} else round(compute_used / float(compute_limit), 6)
        summary["alerts"] = self._threshold_alerts(
            scope_kind=scope_kind,
            subject_id=subject_id,
            money_limit=money_limit,
            money_used=money_used,
            compute_limit=compute_limit,
            compute_used=compute_used,
        )
        return summary

    def _threshold_alerts(
        self,
        *,
        scope_kind: str,
        subject_id: str | None,
        money_limit: float | None,
        money_used: float,
        compute_limit: float | None,
        compute_used: float,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []

        def _severity(pct: float) -> str:
            return "critical" if pct >= 1.0 else "warn"

        def _append(metric: str, used: float, limit: float | None) -> None:
            if limit in {None, 0}:
                return
            utilization = round(float(used) / float(limit), 6)
            for threshold in DEFAULT_BUDGET_ALERT_THRESHOLDS:
                if utilization >= threshold:
                    alerts.append(
                        {
                            "scope_kind": scope_kind,
                            "subject_id": subject_id,
                            "metric": metric,
                            "threshold": threshold,
                            "severity": _severity(threshold),
                            "utilization": utilization,
                            "used": round(float(used), 6),
                            "limit": float(limit),
                        }
                    )

        _append("money", money_used, money_limit)
        _append("compute", compute_used, compute_limit)
        return alerts

    def _next_reset_at(self, config: NodeBudgetConfigRecord) -> str | None:
        if config.period == "manual_reset" or config.reset_policy == "manual":
            return None
        try:
            created_at = datetime.fromisoformat(config.created_at)
        except Exception:
            created_at = datetime.now(timezone.utc)
        now = datetime.now(timezone.utc)
        if config.reset_policy == "rolling":
            delta = timedelta(days=1 if config.period == "daily" else 30)
            return (now + delta).isoformat()
        if config.period == "daily":
            next_day = (now + timedelta(days=1)).date().isoformat()
            return f"{next_day}T00:00:00+00:00"
        if config.period == "monthly":
            year = now.year + (1 if now.month == 12 else 0)
            month = 1 if now.month == 12 else now.month + 1
            return datetime(year, month, 1, tzinfo=timezone.utc).isoformat()
        return (created_at + timedelta(days=30)).isoformat()

    def _normalize_allocations(
        self,
        *,
        node_id: str,
        kind: str,
        allocations: list[dict[str, Any]],
        declaration: NodeBudgetCapabilityRecord,
    ) -> list[NodeBudgetAllocationRecord]:
        kind_key = _clean_text(kind, lower=True)
        if kind_key == "customer" and not declaration.supports_customer_allocations and allocations:
            raise ValueError("customer_budget_allocations_not_supported")
        if kind_key == "provider" and not declaration.supports_provider_allocations and allocations:
            raise ValueError("provider_budget_allocations_not_supported")

        records: list[NodeBudgetAllocationRecord] = []
        seen: set[str] = set()
        for item in allocations:
            if not isinstance(item, dict):
                continue
            subject_id = _clean_text(item.get("subject_id"), lower=True)
            if not subject_id or subject_id in seen:
                continue
            if kind_key == "provider" and declaration.supported_providers and subject_id not in set(declaration.supported_providers):
                raise ValueError("provider_budget_subject_not_supported")
            seen.add(subject_id)
            records.append(
                NodeBudgetAllocationRecord(
                    node_id=node_id,
                    kind=kind_key,
                    subject_id=subject_id,
                    money_limit=_coerce_optional_float(item.get("money_limit")),
                    compute_limit=_coerce_optional_float(item.get("compute_limit")),
                )
            )
        return records

    def _validate_allocation_totals(
        self,
        *,
        config: NodeBudgetConfigRecord,
        customer_records: list[NodeBudgetAllocationRecord],
        provider_records: list[NodeBudgetAllocationRecord],
    ) -> None:
        if config.overcommit_enabled:
            return

        def _sum_money(items: list[NodeBudgetAllocationRecord]) -> float:
            return round(sum(float(item.money_limit or 0) for item in items), 6)

        def _sum_compute(items: list[NodeBudgetAllocationRecord]) -> float:
            return round(sum(float(item.compute_limit or 0) for item in items), 6)

        if config.node_money_limit is not None:
            if _sum_money(customer_records) > float(config.node_money_limit) + 1e-9:
                raise ValueError("customer_budget_allocations_exceed_node_money_limit")
            if _sum_money(provider_records) > float(config.node_money_limit) + 1e-9:
                raise ValueError("provider_budget_allocations_exceed_node_money_limit")
        if config.node_compute_limit is not None:
            if _sum_compute(customer_records) > float(config.node_compute_limit) + 1e-9:
                raise ValueError("customer_budget_allocations_exceed_node_compute_limit")
            if _sum_compute(provider_records) > float(config.node_compute_limit) + 1e-9:
                raise ValueError("provider_budget_allocations_exceed_node_compute_limit")
