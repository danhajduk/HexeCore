from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
import re
import time
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


NODE_DOMAIN_EVENT_TOPIC_FILTER = "hexe/nodes/+/events/#"
NODE_DOMAIN_EVENT_PROMOTION_POLICY = "node-domain-event-promotion-v1"
_EVENT_TYPE_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
_TOPIC_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
_SECRET_VALUE_RE = re.compile(
    r"(bearer\s+[A-Za-z0-9._~+/=-]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"(?:sk|pk|rk|ghp|gho|ghu|github_pat)_[A-Za-z0-9_=-]{12,})",
    re.IGNORECASE,
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_size(payload: Any) -> int:
    try:
        return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    except Exception:
        return 0


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


class NodeDomainEventSource(BaseModel):
    model_config = ConfigDict(extra="allow")

    node_id: str = Field(..., min_length=1)
    component: str = Field(default="node", min_length=1)
    node_type: str | None = None


class NodeOriginatedDomainEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(default=1, ge=1)
    event_id: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)
    source: NodeDomainEventSource
    subject: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)
    occurred_at: str | None = None
    severity: str | None = None
    priority: str | None = None
    safety_critical: bool = False

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, value: str) -> str:
        clean = _clean_text(value).replace("/", ".")
        if not _EVENT_TYPE_RE.match(clean):
            raise ValueError("event_type must be a dotted lower-case domain event name")
        return clean

    @model_validator(mode="after")
    def _ensure_subject_family(self) -> "NodeOriginatedDomainEvent":
        if not self.subject.get("family"):
            family = self.event_type.split(".", 1)[0]
            self.subject["family"] = family
        return self


class CorePromotedNodeDomainEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    promotion_id: str = Field(..., min_length=1)
    event_id: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)
    promoted_event_type: str = Field(..., min_length=1)
    received_at: str = Field(..., min_length=1)
    promoted_at: str = Field(..., min_length=1)
    source: dict[str, Any]
    core: dict[str, Any]
    subject: dict[str, Any]
    routing: dict[str, Any]
    data: dict[str, Any]
    policy: dict[str, Any]

    @field_validator("promoted_event_type")
    @classmethod
    def _validate_promoted_event_type(cls, value: str) -> str:
        clean = _clean_text(value)
        if not _EVENT_TYPE_RE.match(clean):
            raise ValueError("promoted_event_type must be a dotted lower-case domain event name")
        return clean


@dataclass
class _PrivacyResult:
    data: dict[str, Any]
    redacted: bool = False
    rejected: bool = False
    reasons: list[str] = field(default_factory=list)
    suspected_secret: bool = False


@dataclass
class _NodeNoiseWindow:
    events: deque[tuple[float, int]] = field(default_factory=deque)
    invalid_events: deque[float] = field(default_factory=deque)
    limited_since: float | None = None
    blocked: bool = False


@dataclass(frozen=True)
class _NoiseDecision:
    state: str
    accept: bool
    reasons: list[str]


class NodeDomainEventPromoterService:
    def __init__(self, mqtt_manager, state_store, observability_store=None, *, core_id: str | None = None) -> None:
        self._mqtt = mqtt_manager
        self._state_store = state_store
        self._observability = observability_store
        self._core_id = _clean_text(core_id or os.getenv("HEXE_CORE_ID") or os.getenv("SYNTHIA_CORE_ID") or "hexe-core")
        self._log = logging.getLogger("synthia.core.node_domain_events")
        self._listener_ids: list[str] = []
        self._noise: dict[str, _NodeNoiseWindow] = {}
        self._dedupe: dict[str, float] = {}

    async def start(self) -> None:
        if self._listener_ids:
            return
        self._listener_ids.append(
            self._mqtt.register_message_listener(
                topic_filter=NODE_DOMAIN_EVENT_TOPIC_FILTER,
                callback=self._handle_runtime_message,
            )
        )
        self._log.info("node_domain_event_promoter_started topic_filter=%s", NODE_DOMAIN_EVENT_TOPIC_FILTER)

    async def stop(self) -> None:
        for listener_id in list(self._listener_ids):
            self._mqtt.unregister_message_listener(listener_id)
        self._listener_ids.clear()

    async def _handle_runtime_message(self, topic: str, payload: dict[str, Any], retained: bool) -> None:
        received_at = _utcnow_iso()
        route = self._parse_topic(topic)
        if route is None:
            await self._record_decision("rejected", topic=topic, reason="invalid_topic", severity="warning")
            return
        node_id = route["node_id"]
        payload_size = _json_size(payload)
        if retained:
            await self._reject(node_id=node_id, topic=topic, reason="retained_events_not_supported", payload_size=payload_size)
            return
        if payload_size > 64 * 1024:
            await self._reject(node_id=node_id, topic=topic, reason="payload_too_large", payload_size=payload_size)
            return
        principal = await self._active_node_principal(node_id)
        if principal is None:
            await self._reject(node_id=node_id, topic=topic, reason="node_principal_unavailable", payload_size=payload_size)
            return
        try:
            event = NodeOriginatedDomainEvent.model_validate(payload)
        except ValidationError as exc:
            await self._reject(
                node_id=node_id,
                topic=topic,
                reason="node_domain_event_invalid",
                payload_size=payload_size,
                details={"errors": exc.errors()},
            )
            return
        if event.source.node_id != node_id:
            await self._reject(node_id=node_id, topic=topic, reason="node_id_topic_mismatch", payload_size=payload_size)
            return
        if event.event_type != route["promoted_event_type"]:
            await self._reject(
                node_id=node_id,
                topic=topic,
                reason="event_type_topic_mismatch",
                payload_size=payload_size,
                details={"event_type": event.event_type, "topic_event_type": route["promoted_event_type"]},
            )
            return

        privacy = self._apply_privacy_policy(event.data)
        if privacy.rejected:
            await self._reject(
                node_id=node_id,
                topic=topic,
                reason="privacy_policy_rejected",
                payload_size=payload_size,
                details={"decision_reasons": privacy.reasons},
                suspected_secret=privacy.suspected_secret,
            )
            return

        noise = self._record_valid_event(
            node_id=node_id,
            family=str(event.subject.get("family") or route["domain"]),
            payload_size=payload_size,
            safety_critical=self._is_safety_critical(event),
        )
        if not noise.accept:
            await self._record_decision(
                "limited",
                node_id=node_id,
                topic=topic,
                reason="node_domain_event_limited",
                severity="warning",
                payload_size=payload_size,
                noise_state=noise.state,
                details={"decision_reasons": noise.reasons},
            )
            return

        dedupe_key = self._dedupe_key(node_id=node_id, topic=topic, event=event)
        if self._is_duplicate(dedupe_key):
            await self._record_decision(
                "deduped",
                node_id=node_id,
                topic=topic,
                reason="duplicate_event",
                payload_size=payload_size,
                noise_state=noise.state,
                details={"event_id": event.event_id, "dedupe_key": dedupe_key},
            )
            return

        promoted = self._build_promoted_event(
            event=event,
            route=route,
            topic=topic,
            received_at=received_at,
            data=privacy.data,
            redacted=privacy.redacted,
            decision_reasons=[*privacy.reasons, *noise.reasons],
            noise_state=noise.state,
            dedupe_key=dedupe_key,
        )
        publish_results = await self._publish_promoted_event(promoted)
        if not all(bool(item.get("ok")) for item in publish_results):
            await self._record_decision(
                "rejected",
                node_id=node_id,
                topic=topic,
                reason="promotion_publish_failed",
                severity="error",
                payload_size=payload_size,
                details={"publish_results": publish_results},
            )
            return
        await self._record_decision(
            "accepted_with_redaction" if privacy.redacted else "accepted",
            node_id=node_id,
            topic=topic,
            reason="promoted",
            payload_size=payload_size,
            noise_state=noise.state,
            details={
                "event_id": event.event_id,
                "promoted_event_type": promoted.promoted_event_type,
                "domain_topic": promoted.routing["domain_topic"],
                "source_topic": promoted.routing["source_topic"],
                "dedupe_key": dedupe_key,
                "publish_results": publish_results,
                "decision_reasons": promoted.policy.get("decision_reasons", []),
            },
        )

    async def _active_node_principal(self, node_id: str):
        state = await self._state_store.get_state()
        principal = state.principals.get(f"node:{node_id}")
        if principal is None:
            return None
        if principal.principal_type != "synthia_node":
            return None
        if principal.status != "active":
            return None
        if principal.linked_node_id != node_id:
            return None
        return principal

    async def _publish_promoted_event(self, event: CorePromotedNodeDomainEvent) -> list[dict[str, Any]]:
        payload = event.model_dump(mode="json", exclude_none=True)
        return [
            await self._mqtt.publish(topic=event.routing["source_topic"], payload=payload, retain=False, qos=1),
            await self._mqtt.publish(topic=event.routing["domain_topic"], payload=payload, retain=False, qos=1),
        ]

    def _build_promoted_event(
        self,
        *,
        event: NodeOriginatedDomainEvent,
        route: dict[str, str],
        topic: str,
        received_at: str,
        data: dict[str, Any],
        redacted: bool,
        decision_reasons: list[str],
        noise_state: str,
        dedupe_key: str,
    ) -> CorePromotedNodeDomainEvent:
        domain_topic = f"hexe/events/{route['domain_path']}"
        source_topic = f"hexe/events/nodes/{route['node_id']}/{route['domain_path']}"
        payload = CorePromotedNodeDomainEvent(
            promotion_id=str(uuid4()),
            event_id=event.event_id,
            event_type=event.event_type,
            promoted_event_type=route["promoted_event_type"],
            received_at=received_at,
            promoted_at=_utcnow_iso(),
            source={
                "kind": "node",
                "node_id": route["node_id"],
                "component": event.source.component,
                "node_type": event.source.node_type,
                "topic": topic,
            },
            core={
                "core_id": self._core_id,
                "promotion_policy": NODE_DOMAIN_EVENT_PROMOTION_POLICY,
                "validation_status": "accepted_with_redaction" if redacted else "accepted",
                "redaction_version": "v1" if redacted else None,
                "rate_limit_bucket": f"node:{route['node_id']}:{route['domain']}",
            },
            subject=event.subject,
            routing={
                "domain_topic": domain_topic,
                "source_topic": source_topic,
                "dedupe_key": dedupe_key,
            },
            data=data,
            policy={
                "schema_valid": True,
                "privacy_valid": True,
                "noise_state": noise_state,
                "decision_reasons": sorted({reason for reason in decision_reasons if reason}),
            },
        )
        return payload

    def _apply_privacy_policy(self, data: dict[str, Any]) -> _PrivacyResult:
        rejected: list[str] = []
        redacted: list[str] = []

        def walk(value: Any, path: str = "") -> Any:
            if isinstance(value, dict):
                out: dict[str, Any] = {}
                for raw_key, raw_child in value.items():
                    key = str(raw_key)
                    normalized = _normalize_key(key)
                    child_path = f"{path}.{key}" if path else key
                    if normalized in {
                        "raw_email_body",
                        "email_body",
                        "body_html",
                        "html",
                        "attachment",
                        "attachments",
                        "full_payment_number",
                        "full_bank_account_number",
                        "bank_account_number",
                        "verification_code",
                        "full_street_address",
                        "street_address",
                        "full_address",
                    }:
                        rejected.append(f"forbidden_field:{child_path}")
                        continue
                    if normalized in {
                        "token",
                        "access_token",
                        "refresh_token",
                        "oauth_token",
                        "api_key",
                        "apikey",
                        "session_cookie",
                        "cookie",
                        "password",
                        "secret",
                        "client_secret",
                    }:
                        redacted.append(f"secret_field_redacted:{child_path}")
                        out[key] = "[REDACTED]"
                        continue
                    out[key] = walk(raw_child, child_path)
                return out
            if isinstance(value, list):
                return [walk(item, f"{path}[]") for item in value[:100]]
            if isinstance(value, str) and _SECRET_VALUE_RE.search(value):
                redacted.append(f"secret_value_redacted:{path or 'value'}")
                return _SECRET_VALUE_RE.sub("[REDACTED]", value)
            return value

        sanitized = walk(data)
        reasons = sorted({*rejected, *redacted})
        return _PrivacyResult(
            data=sanitized if isinstance(sanitized, dict) else {},
            redacted=bool(redacted),
            rejected=bool(rejected),
            reasons=reasons,
            suspected_secret=bool(redacted or rejected),
        )

    def _record_valid_event(self, *, node_id: str, family: str, payload_size: int, safety_critical: bool) -> _NoiseDecision:
        window = self._noise.setdefault(node_id, _NodeNoiseWindow())
        now = time.time()
        self._prune_noise_window(window, now)
        if window.blocked:
            return _NoiseDecision("blocked", False, ["node_blocked"])
        window.events.append((now, int(payload_size)))
        events_60s = [item for item in window.events if now - item[0] <= 60.0]
        invalid_10m = len(window.invalid_events)
        bytes_60s = sum(size for ts, size in events_60s if now - ts <= 60.0)
        reasons: list[str] = []
        state = "normal"
        if len(events_60s) > 180 or invalid_10m > 50 or bytes_60s > 1024 * 1024:
            state = "limited"
            reasons.append(f"limited:{family}")
            if window.limited_since is None:
                window.limited_since = now
            if now - window.limited_since >= 300.0:
                window.blocked = True
                return _NoiseDecision("blocked", False, ["limited_state_sustained"])
        elif len(events_60s) > 60 or invalid_10m > 10:
            state = "watch"
            reasons.append(f"watch:{family}")
            window.limited_since = None
        else:
            window.limited_since = None
        if state == "limited" and not safety_critical:
            return _NoiseDecision(state, False, reasons)
        return _NoiseDecision(state, True, reasons)

    def _record_invalid_event(self, *, node_id: str, suspected_secret: bool = False) -> _NoiseDecision:
        window = self._noise.setdefault(node_id, _NodeNoiseWindow())
        now = time.time()
        self._prune_noise_window(window, now)
        window.invalid_events.append(now)
        if suspected_secret:
            window.blocked = True
            return _NoiseDecision("blocked", False, ["suspected_secret_or_raw_payload"])
        if len(window.invalid_events) > 100:
            window.blocked = True
            return _NoiseDecision("blocked", False, ["repeated_malformed_bursts"])
        if len(window.invalid_events) > 50:
            return _NoiseDecision("limited", False, ["invalid_events_limited"])
        if len(window.invalid_events) > 10:
            return _NoiseDecision("watch", True, ["invalid_events_watch"])
        return _NoiseDecision("normal", True, [])

    @staticmethod
    def _prune_noise_window(window: _NodeNoiseWindow, now: float) -> None:
        while window.events and now - window.events[0][0] > 600.0:
            window.events.popleft()
        while window.invalid_events and now - window.invalid_events[0] > 600.0:
            window.invalid_events.popleft()

    @staticmethod
    def _is_safety_critical(event: NodeOriginatedDomainEvent) -> bool:
        if event.safety_critical:
            return True
        severity = _clean_text(event.severity).lower()
        priority = _clean_text(event.priority).lower()
        return severity in {"critical", "urgent"} or priority in {"critical", "urgent", "safety"}

    def _is_duplicate(self, dedupe_key: str) -> bool:
        now = time.time()
        expired = [key for key, seen_at in self._dedupe.items() if now - seen_at > 600.0]
        for key in expired:
            self._dedupe.pop(key, None)
        if dedupe_key in self._dedupe:
            return True
        self._dedupe[dedupe_key] = now
        return False

    @staticmethod
    def _dedupe_key(*, node_id: str, topic: str, event: NodeOriginatedDomainEvent) -> str:
        subject = event.subject or {}
        subject_ids = [
            _clean_text(subject.get(key))
            for key in ("message_id", "record_id", "transaction_id")
            if _clean_text(subject.get(key))
        ]
        return "|".join([node_id, topic, event.event_id, *subject_ids])

    async def _reject(
        self,
        *,
        node_id: str,
        topic: str,
        reason: str,
        payload_size: int,
        details: dict[str, Any] | None = None,
        suspected_secret: bool = False,
    ) -> None:
        noise = self._record_invalid_event(node_id=node_id, suspected_secret=suspected_secret)
        await self._record_decision(
            "rejected",
            node_id=node_id,
            topic=topic,
            reason=reason,
            severity="warning",
            payload_size=payload_size,
            noise_state=noise.state,
            details={**(details or {}), "noise_reasons": noise.reasons},
        )

    async def _record_decision(
        self,
        decision: str,
        *,
        topic: str,
        reason: str,
        node_id: str | None = None,
        severity: str = "info",
        payload_size: int | None = None,
        noise_state: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self._observability is None:
            return
        metadata = {
            "decision": decision,
            "reason": reason,
            "topic": topic,
            "node_id": node_id,
            "payload_size": payload_size,
            "noise_state": noise_state,
            **(details or {}),
        }
        try:
            await self._observability.append_event(
                event_type="node_domain_event_promotion",
                source="node_domain_event_promoter",
                severity=severity,
                metadata={key: value for key, value in metadata.items() if value is not None},
            )
        except Exception:
            self._log.exception("node_domain_event_observability_failed node_id=%s topic=%s", node_id, topic)

    @staticmethod
    def _parse_topic(topic: str) -> dict[str, str] | None:
        parts = [part for part in str(topic or "").split("/") if part]
        if len(parts) < 6:
            return None
        if parts[0] != "hexe" or parts[1] != "nodes" or parts[3] != "events":
            return None
        node_id = parts[2].strip()
        domain_parts = parts[4:]
        if not node_id or len(domain_parts) < 2:
            return None
        if any(not _TOPIC_SEGMENT_RE.match(part) for part in [node_id, *domain_parts]):
            return None
        normalized_event_type = ".".join(part.replace("-", "_").lower() for part in domain_parts)
        if not _EVENT_TYPE_RE.match(normalized_event_type):
            return None
        return {
            "node_id": node_id,
            "domain": domain_parts[0],
            "domain_path": "/".join(domain_parts),
            "promoted_event_type": normalized_event_type,
        }
