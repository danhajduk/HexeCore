from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .effective_access import MqttEffectiveAccessCompiler, MqttEffectiveAccessEntry
from .integration_models import MqttIntegrationState
from .topic_families import BOOTSTRAP_TOPIC


DEFAULT_RESERVED_PREFIXES: tuple[str, ...] = (
    "synthia/#",
    "synthia/bootstrap/#",
    "synthia/runtime/#",
    "synthia/system/#",
    "synthia/core/#",
    "synthia/supervisor/#",
    "synthia/scheduler/#",
    "synthia/policy/#",
    "synthia/telemetry/#",
    "synthia/events/#",
    "synthia/remote/#",
    "synthia/bridges/#",
    "synthia/import/#",
)
DEFAULT_BOOTSTRAP_TOPIC = BOOTSTRAP_TOPIC


@dataclass(frozen=True)
class CompiledAclRule:
    principal_id: str
    action: str
    topic: str
    effect: str


@dataclass(frozen=True)
class MqttAclCompilationResult:
    rules: list[CompiledAclRule]
    acl_text: str
    effective_access: list[MqttEffectiveAccessEntry]


@dataclass(frozen=True)
class NormalizedEffectiveAccess:
    principal_id: str
    principal_type: str
    bootstrap_only: bool
    all_non_reserved: bool
    read_rules: list[str]
    write_rules: list[str]
    deny_rules: list[str]


def _sorted_unique(items: Iterable[str]) -> list[str]:
    return sorted({str(item).strip() for item in items if str(item).strip()})


class MqttAclCompiler:
    def __init__(
        self,
        *,
        bootstrap_topic: str = DEFAULT_BOOTSTRAP_TOPIC,
        reserved_prefixes: Iterable[str] | None = None,
    ) -> None:
        self._bootstrap_topic = str(bootstrap_topic or DEFAULT_BOOTSTRAP_TOPIC).strip() or DEFAULT_BOOTSTRAP_TOPIC
        self._reserved = _sorted_unique(reserved_prefixes or DEFAULT_RESERVED_PREFIXES)
        self._effective_access = MqttEffectiveAccessCompiler(
            bootstrap_topic=self._bootstrap_topic,
            reserved_prefixes=list(self._reserved),
        )

    def compile(self, state: MqttIntegrationState) -> MqttAclCompilationResult:
        entries = self._effective_access.compile(state)
        normalized_model = self._normalize_effective_access_model(self._build_effective_access_model(entries))
        rules = self._render_mosquitto_rules(normalized_model)
        normalized = sorted(set(rules), key=lambda item: (item.principal_id, item.action, item.topic, item.effect))
        return MqttAclCompilationResult(rules=normalized, acl_text=self._to_acl_text(state, normalized), effective_access=entries)

    def compile_effective_access(self, state: MqttIntegrationState) -> list[MqttEffectiveAccessEntry]:
        return self._effective_access.compile(state)

    def inspect_effective_access(self, state: MqttIntegrationState, principal_id: str) -> MqttEffectiveAccessEntry | None:
        return self._effective_access.inspect_principal(state, principal_id)

    @staticmethod
    def _build_effective_access_model(entries: list[MqttEffectiveAccessEntry]) -> list[NormalizedEffectiveAccess]:
        model: list[NormalizedEffectiveAccess] = []
        for entry in entries:
            deny_rules: list[str] = []
            if entry.principal_id == "anonymous":
                deny_rules = ["#"]
            elif entry.principal_type == "generic_user":
                deny_rules = list(entry.reserved_prefix_denies)
            model.append(
                NormalizedEffectiveAccess(
                    principal_id=entry.principal_id,
                    principal_type=entry.principal_type,
                    bootstrap_only=bool(entry.anonymous_bootstrap_only),
                    all_non_reserved=bool(entry.generic_non_reserved_only),
                    read_rules=_sorted_unique(entry.subscribe_scopes),
                    write_rules=_sorted_unique(entry.publish_scopes),
                    deny_rules=_sorted_unique(deny_rules),
                )
            )
        return model

    @staticmethod
    def _normalize_effective_access_model(entries: list[NormalizedEffectiveAccess]) -> list[NormalizedEffectiveAccess]:
        normalized: list[NormalizedEffectiveAccess] = []
        for entry in entries:
            normalized.append(
                NormalizedEffectiveAccess(
                    principal_id=entry.principal_id,
                    principal_type=entry.principal_type,
                    bootstrap_only=bool(entry.bootstrap_only),
                    all_non_reserved=bool(entry.all_non_reserved),
                    read_rules=_sorted_unique(entry.read_rules),
                    write_rules=_sorted_unique(entry.write_rules),
                    deny_rules=_sorted_unique(entry.deny_rules),
                )
            )
        return normalized

    @staticmethod
    def _render_mosquitto_rules(entries: list[NormalizedEffectiveAccess]) -> list[CompiledAclRule]:
        rules: list[CompiledAclRule] = []
        for entry in entries:
            if entry.principal_id == "anonymous":
                for topic in entry.read_rules:
                    rules.append(CompiledAclRule("anonymous", "subscribe", topic, "allow"))
                for topic in entry.deny_rules or ["#"]:
                    rules.append(CompiledAclRule("anonymous", "publish", topic, "deny"))
                    rules.append(CompiledAclRule("anonymous", "subscribe", topic, "deny"))
                continue
            for topic in entry.write_rules:
                rules.append(CompiledAclRule(entry.principal_id, "publish", topic, "allow"))
            for topic in entry.read_rules:
                rules.append(CompiledAclRule(entry.principal_id, "subscribe", topic, "allow"))
            for prefix in entry.deny_rules:
                rules.append(CompiledAclRule(entry.principal_id, "publish", prefix, "deny"))
                rules.append(CompiledAclRule(entry.principal_id, "subscribe", prefix, "deny"))
        return rules

    def _to_acl_text(self, state: MqttIntegrationState, rules: list[CompiledAclRule]) -> str:
        lines: list[str] = []
        lines.append("# generated by synthia core mqtt acl compiler")
        anonymous_rules = sorted(
            [rule for rule in rules if rule.principal_id == "anonymous"],
            key=lambda item: (item.effect, item.action, item.topic),
        )
        for rule in anonymous_rules:
            acl = self._to_mosquitto_acl_line(rule)
            if acl is not None:
                lines.append(acl)

        principal_ids = sorted({rule.principal_id for rule in rules if rule.principal_id != "anonymous"})
        for principal_id in principal_ids:
            username = self._principal_username(state, principal_id)
            if not username:
                continue
            lines.append("")
            lines.append(f"user {username}")
            principal_rules = sorted(
                [rule for rule in rules if rule.principal_id == principal_id],
                key=lambda item: (item.effect, item.action, item.topic),
            )
            for rule in principal_rules:
                acl = self._to_mosquitto_acl_line(rule)
                if acl is not None:
                    lines.append(acl)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _to_mosquitto_acl_line(rule: CompiledAclRule) -> str | None:
        if rule.effect == "deny":
            return f"topic deny {rule.topic}"
        if rule.action == "publish":
            return f"topic write {rule.topic}"
        if rule.action == "subscribe":
            return f"topic read {rule.topic}"
        return None

    @staticmethod
    def _principal_username(state: MqttIntegrationState, principal_id: str) -> str:
        principal = state.principals.get(principal_id)
        if principal is None:
            return principal_id.replace(":", "_")
        username = str(principal.username or "").strip()
        if username:
            return username
        return principal.principal_id.replace(":", "_")
