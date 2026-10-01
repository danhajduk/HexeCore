from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.system.audit import AuditLogStore
from app.system.auth.device_enrollment import WebAppEnrollmentStore, _default_notification_categories
from .node_domain_events import CorePromotedNodeDomainEvent


POLICY_VERSION = "hexe.web-notification-policy.v1"
PROMOTED_EVENT_TOPIC_FILTER = "hexe/events/#"
CATEGORY_BY_PREFIX = {
    "security.": "security",
    "approval.": "approval-required",
    "task.": "task-completion",
    "timer.": "timers-reminders",
    "reminder.": "timers-reminders",
    "device.": "device-health",
    "node.": "device-health",
    "email.": "email-alerts",
}
SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}
PRIVILEGED_CATEGORIES = {"security", "approval-required", "device-health"}
SENSITIVE_TEXT_RE = re.compile(
    r"\b(password|passcode|token|secret|credential|verification code|account number|card number|transcript|email body|address)\b",
    re.IGNORECASE,
)


class TrustedNotificationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=1, max_length=160)
    event_type: str = Field(..., min_length=3, max_length=160, pattern=r"^[a-z0-9_]+(?:\.[a-z0-9_]+)+$")
    source_kind: Literal["core", "node", "addon", "service", "system"]
    source_id: str = Field(..., min_length=1, max_length=160)
    severity: Literal["info", "warning", "critical"] = "info"
    subject_user_id: str | None = Field(default=None, max_length=160)
    summary: str | None = Field(default=None, max_length=500)
    sensitive: bool = False
    navigation_path: str | None = Field(default=None, max_length=240)

    @field_validator("navigation_path")
    @classmethod
    def validate_navigation_path(cls, value: str | None) -> str | None:
        if value is not None and (not value.startswith("/") or value.startswith("//") or "://" in value):
            raise ValueError("navigation_path_must_be_core_relative")
        return value


class NotificationIntentStore:
    def __init__(self, db_path: str, *, max_rows: int = 10000) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()
        self._max_rows = max(100, max_rows)
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS web_app_notification_intents (
              intent_id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_id TEXT NOT NULL, core_id TEXT NOT NULL, user_id TEXT NOT NULL,
              device_id TEXT NOT NULL, subscription_ref TEXT NOT NULL,
              gateway_audience TEXT NOT NULL, category TEXT NOT NULL,
              severity TEXT NOT NULL, privacy_level TEXT NOT NULL,
              title TEXT NOT NULL, body TEXT NOT NULL, navigation_path TEXT NOT NULL,
              created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
              coalesced_count INTEGER NOT NULL DEFAULT 1,
              attempt_count INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT,
              expires_at TEXT, last_error TEXT, delivered_at TEXT,
              UNIQUE(event_id, device_id, category)
            );
            """
        )
        columns = {str(row["name"]) for row in self._conn.execute("PRAGMA table_info(web_app_notification_intents)").fetchall()}
        for name, definition in (
            ("coalesced_count", "INTEGER NOT NULL DEFAULT 1"),
            ("attempt_count", "INTEGER NOT NULL DEFAULT 0"),
            ("next_attempt_at", "TEXT"), ("expires_at", "TEXT"),
            ("last_error", "TEXT"), ("delivered_at", "TEXT"),
        ):
            if name not in columns:
                self._conn.execute(f"ALTER TABLE web_app_notification_intents ADD COLUMN {name} {definition}")

    async def create(self, intent: dict[str, Any]) -> bool:
        async with self._lock:
            return await asyncio.to_thread(self._create, intent)

    def _create(self, intent: dict[str, Any]) -> bool:
        count = int(self._conn.execute("SELECT COUNT(*) FROM web_app_notification_intents").fetchone()[0])
        if count >= self._max_rows:
            self._conn.execute(
                "DELETE FROM web_app_notification_intents WHERE intent_id IN (SELECT intent_id FROM web_app_notification_intents WHERE status IN ('delivered','dead','expired') ORDER BY intent_id LIMIT ?)",
                (count - self._max_rows + 1,),
            )
            if int(self._conn.execute("SELECT COUNT(*) FROM web_app_notification_intents").fetchone()[0]) >= self._max_rows:
                return False
        created_at = datetime.fromisoformat(str(intent["created_at"]).replace("Z", "+00:00"))
        expires_at = (created_at + timedelta(days=1)).isoformat()
        changed = self._conn.execute(
            """INSERT OR IGNORE INTO web_app_notification_intents
               (event_id, core_id, user_id, device_id, subscription_ref, gateway_audience,
                category, severity, privacy_level, title, body, navigation_path, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            tuple(intent[key] for key in (
                "event_id", "core_id", "user_id", "device_id", "subscription_ref",
                "gateway_audience", "category", "severity", "privacy_level", "title",
                "body", "navigation_path", "created_at",
            )) + (expires_at,),
        )
        return changed.rowcount == 1

    async def list_pending(self) -> list[dict[str, Any]]:
        async with self._lock:
            rows = await asyncio.to_thread(
                self._conn.execute("SELECT * FROM web_app_notification_intents WHERE status='pending' ORDER BY intent_id").fetchall
            )
            return [dict(row) for row in rows]

    async def has_event(self, event_id: str, device_id: str, category: str) -> bool:
        async with self._lock:
            row = await asyncio.to_thread(self._conn.execute(
                "SELECT 1 FROM web_app_notification_intents WHERE event_id=? AND device_id=? AND category=?",
                (event_id, device_id, category),
            ).fetchone)
            return row is not None

    async def recent_count(self, device_id: str, category: str, since: str) -> int:
        async with self._lock:
            row = await asyncio.to_thread(self._conn.execute(
                "SELECT COUNT(*) FROM web_app_notification_intents WHERE device_id=? AND category=? AND created_at>=?",
                (device_id, category, since),
            ).fetchone)
            return int(row[0] if row else 0)

    async def coalesce_latest(self, device_id: str, category: str) -> bool:
        async with self._lock:
            changed = await asyncio.to_thread(
                self._conn.execute,
                """UPDATE web_app_notification_intents SET coalesced_count=coalesced_count+1
                   WHERE intent_id=(SELECT intent_id FROM web_app_notification_intents
                     WHERE device_id=? AND category=? AND status='pending' ORDER BY intent_id DESC LIMIT 1)""",
                (device_id, category),
            )
            return changed.rowcount == 1

    async def due(self, now: str, limit: int = 50) -> list[dict[str, Any]]:
        async with self._lock:
            await asyncio.to_thread(
                self._conn.execute,
                "UPDATE web_app_notification_intents SET status='expired', last_error='intent_expired' WHERE status IN ('pending','retry') AND expires_at IS NOT NULL AND expires_at<=?",
                (now,),
            )
            rows = await asyncio.to_thread(self._conn.execute(
                """SELECT * FROM web_app_notification_intents
                   WHERE status IN ('pending','retry') AND (next_attempt_at IS NULL OR next_attempt_at<=?)
                     AND (expires_at IS NULL OR expires_at>?) ORDER BY intent_id LIMIT ?""",
                (now, now, limit),
            ).fetchall)
            return [dict(row) for row in rows]

    async def mark_delivery(self, intent_id: int, *, status: str, attempt_count: int, next_attempt_at: str | None = None, last_error: str | None = None, delivered_at: str | None = None) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._conn.execute,
                "UPDATE web_app_notification_intents SET status=?, attempt_count=?, next_attempt_at=?, last_error=?, delivered_at=? WHERE intent_id=?",
                (status, attempt_count, next_attempt_at, last_error, delivered_at, intent_id),
            )

    async def status_counts(self) -> dict[str, int]:
        async with self._lock:
            rows = await asyncio.to_thread(self._conn.execute(
                "SELECT status, COUNT(*) AS count FROM web_app_notification_intents GROUP BY status"
            ).fetchall)
            return {str(row["status"]): int(row["count"]) for row in rows}


class WebNotificationPolicyService:
    def __init__(self, devices: WebAppEnrollmentStore, intents: NotificationIntentStore, *, core_id: str, audit: AuditLogStore | None = None, rate_limit: int = 5, rate_window_s: int = 300) -> None:
        self._devices = devices
        self._intents = intents
        self._core_id = core_id
        self._audit = audit
        self._rate_limit = max(1, rate_limit)
        self._rate_window_s = max(1, rate_window_s)

    async def route(self, event: TrustedNotificationEvent, *, trusted_source: bool, at: datetime | None = None) -> dict[str, Any]:
        if not trusted_source:
            await self._audit_decision(event, None, None, "suppressed", "untrusted_source")
            return {"ok": False, "reason": "untrusted_source", "created": 0, "suppressed": 1}
        category = self._category(event.event_type)
        if category is None:
            await self._audit_decision(event, None, None, "suppressed", "category_unsupported")
            return {"ok": True, "reason": "category_unsupported", "created": 0, "suppressed": 1}

        created = suppressed = deduplicated = 0
        now = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        for target in await self._devices.list_notification_targets(self._core_id):
            reason = self._suppression_reason(event, category, target, now)
            if reason:
                suppressed += 1
                await self._audit_decision(event, target["user_id"], target["device_id"], "suppressed", reason, category)
                continue
            if await self._intents.has_event(event.event_id, str(target["device_id"]), category):
                deduplicated += 1
                await self._audit_decision(event, target["user_id"], target["device_id"], "suppressed", "duplicate_event", category)
                continue
            recent = await self._intents.recent_count(
                str(target["device_id"]), category, (now - timedelta(seconds=self._rate_window_s)).isoformat()
            )
            if recent >= self._rate_limit and event.severity != "critical":
                await self._intents.coalesce_latest(str(target["device_id"]), category)
                suppressed += 1
                await self._audit_decision(event, target["user_id"], target["device_id"], "suppressed", "rate_limited_coalesced", category)
                continue
            intent = self._intent(event, category, target, now)
            if await self._intents.create(intent):
                created += 1
                await self._audit_decision(event, target["user_id"], target["device_id"], "created", None, category)
            else:
                deduplicated += 1
                await self._audit_decision(event, target["user_id"], target["device_id"], "suppressed", "duplicate_event", category)
        return {"ok": True, "created": created, "suppressed": suppressed, "deduplicated": deduplicated}

    @staticmethod
    def _category(event_type: str) -> str | None:
        return next((category for prefix, category in CATEGORY_BY_PREFIX.items() if event_type.startswith(prefix)), None)

    def _suppression_reason(self, event: TrustedNotificationEvent, category: str, target: dict[str, Any], now: datetime) -> str | None:
        if event.subject_user_id:
            if str(target["user_id"]) != event.subject_user_id and category not in PRIVILEGED_CATEGORIES:
                return "different_user"
            if str(target["user_id"]) != event.subject_user_id and str(target["role"]) not in {"owner", "admin"}:
                return "permission_denied"
        elif category not in PRIVILEGED_CATEGORIES:
            return "recipient_unspecified"
        elif str(target["role"]) not in {"owner", "admin"}:
            return "permission_denied"

        categories = json.loads(target.get("categories_json") or json.dumps(_default_notification_categories()))
        if not bool(target.get("preferences_enabled", 1)):
            return "notifications_disabled"
        if not bool(categories.get(category, False)):
            return "category_disabled"
        if SEVERITY_RANK[event.severity] < SEVERITY_RANK.get(str(target.get("severity_threshold") or "info"), 0):
            return "below_severity_threshold"
        if self._in_quiet_hours(target, now) and event.severity != "critical":
            return "quiet_hours"
        return None

    @staticmethod
    def _in_quiet_hours(target: dict[str, Any], now: datetime) -> bool:
        start, end = target.get("quiet_hours_start"), target.get("quiet_hours_end")
        if not start or not end:
            return False
        try:
            local = now.astimezone(ZoneInfo(str(target.get("time_zone") or "UTC"))).strftime("%H:%M")
        except ZoneInfoNotFoundError:
            return True
        return start <= local < end if start < end else local >= start or local < end

    def _intent(self, event: TrustedNotificationEvent, category: str, target: dict[str, Any], now: datetime) -> dict[str, Any]:
        privacy = str(target.get("privacy_level") or "generic")
        title = {
            "security": "Security alert", "approval-required": "Approval required",
            "task-completion": "Task update", "timers-reminders": "Reminder",
            "device-health": "Device health alert", "email-alerts": "New email alert",
        }[category]
        body = "Open Hexe to view details."
        if privacy in {"summary", "sensitive"} and not event.sensitive and event.summary and not SENSITIVE_TEXT_RE.search(event.summary):
            body = event.summary.strip()[:160]
        return {
            "event_id": event.event_id, "core_id": self._core_id,
            "user_id": target["user_id"], "device_id": target["device_id"],
            "subscription_ref": target["subscription_ref"], "gateway_audience": target["gateway_audience"],
            "category": category, "severity": event.severity, "privacy_level": privacy,
            "title": title[:80], "body": body[:180],
            "navigation_path": event.navigation_path or f"/app/notifications/{event.event_id}",
            "created_at": now.isoformat(),
        }

    async def _audit_decision(self, event, user_id, device_id, decision, reason, category=None) -> None:
        if self._audit is not None:
            await self._audit.record(
                event_type="web_notification_policy_decision", actor_role="system", actor_id="notification-policy",
                details={"event_id": event.event_id, "category": category, "user_id": user_id, "device_id": device_id, "decision": decision, "reason": reason},
            )


class WebNotificationEventConsumer:
    def __init__(self, mqtt_manager, policy: WebNotificationPolicyService, *, core_id: str) -> None:
        self._mqtt = mqtt_manager
        self._policy = policy
        self._core_id = core_id
        self._listener_id: str | None = None

    async def start(self) -> None:
        if self._listener_id is None:
            self._listener_id = self._mqtt.register_message_listener(
                topic_filter=PROMOTED_EVENT_TOPIC_FILTER,
                callback=self._handle_message,
            )

    async def stop(self) -> None:
        if self._listener_id is not None:
            self._mqtt.unregister_message_listener(self._listener_id)
            self._listener_id = None

    async def _handle_message(self, topic: str, payload: dict[str, Any], retained: bool) -> None:
        if retained:
            return
        try:
            promoted = CorePromotedNodeDomainEvent.model_validate(payload)
        except Exception:
            return
        if (
            promoted.core.get("core_id") != self._core_id
            or promoted.core.get("validation_status") not in {"accepted", "accepted_with_redaction"}
            or not promoted.policy.get("schema_valid")
            or not promoted.policy.get("privacy_valid")
            or promoted.routing.get("domain_topic") != topic
            or not topic.startswith("hexe/events/")
        ):
            return
        data = promoted.data
        raw_severity = str(data.get("severity") or "info").lower()
        severity = raw_severity if raw_severity in SEVERITY_RANK else "warning" if raw_severity in {"error", "urgent"} else "info"
        try:
            event = TrustedNotificationEvent(
                event_id=promoted.event_id,
                event_type=promoted.promoted_event_type,
                source_kind="node",
                source_id=str(promoted.source.get("node_id") or "node"),
                severity=severity,
                subject_user_id=promoted.subject.get("user_id"),
                summary=data.get("summary"),
                sensitive=bool(data.get("sensitive", False)),
                navigation_path=data.get("navigation_path"),
            )
        except Exception:
            return
        await self._policy.route(event, trusted_source=True)
