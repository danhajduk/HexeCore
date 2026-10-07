from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from webauthn import verify_authentication_response, verify_registration_response
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse

from app.api.admin import admin_request_actor, require_admin_token
from app.system.audit import AuditLogStore
from app.system.platform_identity import load_platform_identity
from app.system.settings.store import SettingsStore
from app.system.users.store import UsersStore
from .human import _access_token, _iso_after, _refresh_verifier, authenticate_human_token
from .tokens import ServiceTokenKeyStore

CONTRACT_VERSION = "hexe.web-app-enrollment.v1"
DEVICE_LOGIN_VERSION = "hexe.web-app-device-login.v1"
DEFAULT_TTL_S = 10 * 60
NOTIFICATION_CATEGORIES = {
    "security",
    "approval-required",
    "task-completion",
    "timers-reminders",
    "device-health",
    "email-alerts",
}


def _default_notification_categories() -> dict[str, bool]:
    return {category: category != "email-alerts" for category in sorted(NOTIFICATION_CATEGORIES)}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _decode_b64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _encode_b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _proof_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class EnrollmentCreateRequest(BaseModel):
    user_id: str | None = None
    display_name: str = Field(default="Hexe Web App", min_length=1, max_length=120)
    replace_device_id: str | None = Field(default=None, max_length=160)
    ttl_seconds: int = Field(default=DEFAULT_TTL_S, ge=60, le=3600)


class EnrollmentCompleteRequest(BaseModel):
    proof: str = Field(..., min_length=32, max_length=512)
    device_id: str = Field(..., min_length=8, max_length=160)
    public_key: str = Field(..., min_length=43, max_length=128)
    signature: str = Field(..., min_length=43, max_length=256)
    platform: str | None = Field(default=None, max_length=80)
    browser_metadata: dict[str, str] = Field(default_factory=dict)
    passkey_credential: dict[str, Any]

    @field_validator("browser_metadata")
    @classmethod
    def validate_browser_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        allowed = {"browser_name", "browser_version", "os_name", "os_version", "app_version"}
        if set(value) - allowed or len(value) > len(allowed):
            raise ValueError("browser_metadata_invalid")
        if any(not item.strip() or len(item) > 80 for item in value.values()):
            raise ValueError("browser_metadata_invalid")
        return value


class EnrollmentPasskeyOptionsRequest(BaseModel):
    proof: str = Field(..., min_length=32, max_length=512)


class DeviceKeyRotationRequest(BaseModel):
    new_public_key: str = Field(..., min_length=43, max_length=128)
    old_key_signature: str = Field(..., min_length=43, max_length=256)
    new_key_signature: str = Field(..., min_length=43, max_length=256)


class DeviceLoginChallengeRequest(BaseModel):
    device_id: str = Field(..., min_length=8, max_length=160)
    username: str | None = Field(default=None, min_length=1, max_length=160)
    password: str | None = Field(default=None, min_length=1, max_length=1024)


class DeviceLoginCompleteRequest(BaseModel):
    challenge_id: str = Field(..., min_length=8, max_length=160)
    signature: str = Field(..., min_length=43, max_length=256)
    passkey_credential: dict[str, Any]


class DeviceUpdateRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=120)


class DeviceStateUpdateRequest(BaseModel):
    enabled: bool


class NotificationSubscriptionRequest(BaseModel):
    subscription_ref: str = Field(..., min_length=8, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._~-]+$")
    gateway_audience: str = Field(..., min_length=1, max_length=160)


class NotificationPreferencesRequest(BaseModel):
    enabled: bool = True
    categories: dict[str, bool] = Field(default_factory=_default_notification_categories)
    quiet_hours_start: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    quiet_hours_end: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    time_zone: str = Field(default="UTC", min_length=1, max_length=64)
    privacy_level: Literal["generic", "summary", "sensitive"] = "generic"
    severity_threshold: Literal["info", "warning", "critical"] = "info"

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, value: dict[str, bool]) -> dict[str, bool]:
        if set(value) != NOTIFICATION_CATEGORIES:
            raise ValueError("notification_categories_invalid")
        return value

    @field_validator("time_zone")
    @classmethod
    def validate_time_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("time_zone_invalid") from exc
        return value

    @model_validator(mode="after")
    def validate_quiet_hours(self):
        if (self.quiet_hours_start is None) != (self.quiet_hours_end is None):
            raise ValueError("quiet_hours_incomplete")
        return self


def _env_positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


class WebAppEnrollmentStore:
    def __init__(self, db_path: str, *, max_devices_per_user: int | None = None, max_devices_per_core: int | None = None) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._max_devices_per_user = max_devices_per_user or _env_positive_int("HEXE_WEB_APP_MAX_DEVICES_PER_USER", 10)
        self._max_devices_per_core = max_devices_per_core or _env_positive_int("HEXE_WEB_APP_MAX_DEVICES_PER_CORE", 100)
        self._conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS web_app_devices (
              device_id TEXT PRIMARY KEY, core_id TEXT NOT NULL, user_id TEXT NOT NULL,
              display_name TEXT NOT NULL, public_key TEXT NOT NULL, platform TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revoked_at TEXT
            );
            CREATE TABLE IF NOT EXISTS web_app_enrollments (
              enrollment_id TEXT PRIMARY KEY, core_id TEXT NOT NULL, user_id TEXT NOT NULL,
              created_by TEXT NOT NULL, display_name TEXT NOT NULL, replace_device_id TEXT,
              proof_hash TEXT NOT NULL, challenge TEXT NOT NULL, status TEXT NOT NULL,
              created_at TEXT NOT NULL, expires_at TEXT NOT NULL, approved_at TEXT,
              approved_by TEXT, consumed_at TEXT, cancelled_at TEXT, device_id TEXT,
              failure_code TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS web_app_enrollment_proof_idx ON web_app_enrollments(proof_hash);
            CREATE TABLE IF NOT EXISTS web_app_notification_subscriptions (
              device_id TEXT PRIMARY KEY, core_id TEXT NOT NULL, user_id TEXT NOT NULL,
              subscription_ref TEXT NOT NULL, gateway_audience TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT,
              cleanup_state TEXT NOT NULL DEFAULT 'active',
              FOREIGN KEY(device_id) REFERENCES web_app_devices(device_id)
            );
            CREATE TABLE IF NOT EXISTS web_app_notification_preferences (
              device_id TEXT PRIMARY KEY, core_id TEXT NOT NULL, user_id TEXT NOT NULL,
              enabled INTEGER NOT NULL, categories_json TEXT NOT NULL,
              quiet_hours_start TEXT, quiet_hours_end TEXT, time_zone TEXT NOT NULL,
              privacy_level TEXT NOT NULL, severity_threshold TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              FOREIGN KEY(device_id) REFERENCES web_app_devices(device_id)
            );
            CREATE TABLE IF NOT EXISTS web_app_device_state (
              device_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1,
              last_seen_at TEXT, browser_metadata_json TEXT NOT NULL DEFAULT '{}',
              updated_at TEXT NOT NULL,
              FOREIGN KEY(device_id) REFERENCES web_app_devices(device_id)
            );
            CREATE TABLE IF NOT EXISTS web_app_device_login_challenges (
              challenge_id TEXT PRIMARY KEY, core_id TEXT NOT NULL, user_id TEXT NOT NULL,
              device_id TEXT NOT NULL, nonce TEXT NOT NULL, created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL, consumed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS web_app_passkeys (
              credential_id TEXT PRIMARY KEY, core_id TEXT NOT NULL, user_id TEXT NOT NULL,
              device_id TEXT NOT NULL UNIQUE, public_key TEXT NOT NULL, sign_count INTEGER NOT NULL,
              created_at TEXT NOT NULL, last_used_at TEXT,
              FOREIGN KEY(device_id) REFERENCES web_app_devices(device_id)
            );
            """
        )

    async def create_login_challenge(self, *, core_id: str, user_id: str, device_id: str, ttl_s: int = 120) -> dict[str, Any]:
        async with self._lock:
            challenge_id, nonce, created = f"dlc_{uuid.uuid4().hex}", secrets.token_urlsafe(32), _now()
            expires = created + timedelta(seconds=ttl_s)
            await asyncio.to_thread(self._conn.execute, "INSERT INTO web_app_device_login_challenges VALUES (?, ?, ?, ?, ?, ?, ?, NULL)", (challenge_id, core_id, user_id, device_id, nonce, created.isoformat(), expires.isoformat()))
            return {"challenge_id": challenge_id, "core_id": core_id, "device_id": device_id, "nonce": nonce, "expires_at": expires.isoformat()}

    async def consume_login_challenge(self, challenge_id: str) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._consume_login_challenge, challenge_id)

    def _consume_login_challenge(self, challenge_id: str) -> dict[str, Any]:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute("SELECT * FROM web_app_device_login_challenges WHERE challenge_id=?", (challenge_id,)).fetchone()
            if row is None: raise RuntimeError("device_login_challenge_invalid")
            result = dict(row)
            if result.get("consumed_at"): raise RuntimeError("device_login_challenge_replayed")
            if datetime.fromisoformat(str(result["expires_at"]).replace("Z", "+00:00")) <= _now(): raise RuntimeError("device_login_challenge_expired")
            changed = self._conn.execute("UPDATE web_app_device_login_challenges SET consumed_at=? WHERE challenge_id=? AND consumed_at IS NULL", (_now_iso(), challenge_id)).rowcount
            if changed != 1: raise RuntimeError("device_login_challenge_replayed")
            self._conn.execute("COMMIT")
            return result
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    async def create(self, *, core_id: str, user_id: str, created_by: str, display_name: str, replace_device_id: str | None, ttl_s: int) -> tuple[dict[str, Any], str]:
        async with self._lock:
            return await asyncio.to_thread(self._create, core_id, user_id, created_by, display_name, replace_device_id, ttl_s)

    def _create(self, core_id, user_id, created_by, display_name, replace_device_id, ttl_s):
        enrollment_id, proof, challenge = f"enr_{uuid.uuid4().hex}", secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        created, expires = _now(), _now() + timedelta(seconds=ttl_s)
        self._conn.execute("INSERT INTO web_app_enrollments VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, NULL, NULL, NULL, NULL, NULL, NULL)", (enrollment_id, core_id, user_id, created_by, display_name, replace_device_id, _proof_hash(proof), challenge, created.isoformat(), expires.isoformat()))
        return self._get(enrollment_id), proof

    async def get(self, enrollment_id: str) -> dict[str, Any] | None:
        async with self._lock:
            return await asyncio.to_thread(self._get, enrollment_id)

    def _get(self, enrollment_id):
        row = self._conn.execute("SELECT * FROM web_app_enrollments WHERE enrollment_id = ?", (enrollment_id,)).fetchone()
        return dict(row) if row else None

    async def approve(self, enrollment_id: str, approved_by: str) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._approve, enrollment_id, approved_by)

    def _approve(self, enrollment_id, approved_by):
        row = self._get(enrollment_id)
        if row is None: raise RuntimeError("enrollment_not_found")
        self._require_live(row)
        if row["status"] == "approved": return row
        if row["status"] != "pending": raise RuntimeError("enrollment_not_pending")
        self._conn.execute("UPDATE web_app_enrollments SET status='approved', approved_at=?, approved_by=? WHERE enrollment_id=? AND status='pending'", (_now_iso(), approved_by, enrollment_id))
        return self._get(enrollment_id)

    async def cancel(self, enrollment_id: str) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._cancel, enrollment_id)

    def _cancel(self, enrollment_id):
        row = self._get(enrollment_id)
        if row is None: raise RuntimeError("enrollment_not_found")
        if row["status"] in {"consumed", "cancelled"}: raise RuntimeError("enrollment_not_active")
        self._conn.execute("UPDATE web_app_enrollments SET status='cancelled', cancelled_at=? WHERE enrollment_id=?", (_now_iso(), enrollment_id))
        return self._get(enrollment_id)

    @staticmethod
    def _require_live(row):
        if datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00")) <= _now():
            raise RuntimeError("enrollment_expired")

    async def consume(self, *, enrollment_id: str, proof: str, device_id: str, public_key: str, platform: str | None, browser_metadata: dict[str, str] | None = None, passkey: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._consume, enrollment_id, proof, device_id, public_key, platform, browser_metadata or {}, passkey)

    def _consume(self, enrollment_id, proof, device_id, public_key, platform, browser_metadata, passkey):
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._get(enrollment_id)
            if row is None: raise RuntimeError("enrollment_not_found")
            self._require_live(row)
            if row["status"] == "consumed": raise RuntimeError("enrollment_already_consumed")
            if row["status"] != "approved": raise RuntimeError("enrollment_not_approved")
            if not secrets.compare_digest(str(row["proof_hash"]), _proof_hash(proof)): raise RuntimeError("enrollment_proof_invalid")
            existing = self._conn.execute("SELECT * FROM web_app_devices WHERE device_id=?", (device_id,)).fetchone()
            replace_id = str(row["replace_device_id"] or "")
            if existing is not None and device_id != replace_id: raise RuntimeError("device_already_exists")
            excluded_device_id = replace_id if replace_id else device_id
            user_count = self._conn.execute(
                "SELECT COUNT(*) FROM web_app_devices d LEFT JOIN web_app_device_state s ON s.device_id=d.device_id WHERE d.user_id=? AND d.revoked_at IS NULL AND COALESCE(s.enabled, 1)=1 AND d.device_id<>?",
                (row["user_id"], excluded_device_id),
            ).fetchone()[0]
            if user_count >= self._max_devices_per_user: raise RuntimeError("device_user_limit_reached")
            core_count = self._conn.execute(
                "SELECT COUNT(*) FROM web_app_devices d LEFT JOIN web_app_device_state s ON s.device_id=d.device_id WHERE d.core_id=? AND d.revoked_at IS NULL AND COALESCE(s.enabled, 1)=1 AND d.device_id<>?",
                (row["core_id"], excluded_device_id),
            ).fetchone()[0]
            if core_count >= self._max_devices_per_core: raise RuntimeError("device_core_limit_reached")
            if replace_id:
                replacement = self._conn.execute("SELECT * FROM web_app_devices WHERE device_id=? AND core_id=? AND user_id=? AND revoked_at IS NULL", (replace_id, row["core_id"], row["user_id"])).fetchone()
                if replacement is None: raise RuntimeError("replacement_device_not_available")
                revoked_at = _now_iso()
                self._conn.execute("UPDATE web_app_devices SET revoked_at=?, updated_at=? WHERE device_id=?", (revoked_at, revoked_at, replace_id))
                self._conn.execute("UPDATE web_app_device_state SET enabled=0, updated_at=? WHERE device_id=?", (revoked_at, replace_id))
                self._conn.execute(
                    "UPDATE web_app_notification_subscriptions SET deleted_at=?, updated_at=?, cleanup_state='pending' WHERE device_id=? AND deleted_at IS NULL",
                    (revoked_at, revoked_at, replace_id),
                )
            now = _now_iso()
            self._conn.execute("INSERT INTO web_app_devices VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL) ON CONFLICT(device_id) DO UPDATE SET public_key=excluded.public_key, platform=excluded.platform, updated_at=excluded.updated_at, revoked_at=NULL", (device_id, row["core_id"], row["user_id"], row["display_name"], public_key, platform, now, now))
            self._conn.execute(
                "INSERT INTO web_app_device_state VALUES (?, 1, ?, ?, ?) ON CONFLICT(device_id) DO UPDATE SET enabled=1, last_seen_at=excluded.last_seen_at, browser_metadata_json=excluded.browser_metadata_json, updated_at=excluded.updated_at",
                (device_id, now, json.dumps(browser_metadata, sort_keys=True, separators=(",", ":")), now),
            )
            if passkey is not None:
                self._conn.execute(
                    "INSERT INTO web_app_passkeys VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                    (passkey["credential_id"], row["core_id"], row["user_id"], device_id, passkey["public_key"], passkey["sign_count"], now),
                )
            changed = self._conn.execute("UPDATE web_app_enrollments SET status='consumed', consumed_at=?, device_id=? WHERE enrollment_id=? AND status='approved'", (now, device_id, enrollment_id)).rowcount
            if changed != 1: raise RuntimeError("enrollment_already_consumed")
            self._conn.execute("COMMIT")
            return self._get(enrollment_id)
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    async def get_device(self, device_id: str) -> dict[str, Any] | None:
        async with self._lock:
            row = await asyncio.to_thread(self._conn.execute(
                """SELECT d.*,
                    CASE WHEN d.revoked_at IS NOT NULL THEN 0 ELSE COALESCE(s.enabled, 1) END AS enabled,
                    COALESCE(s.last_seen_at, d.updated_at) AS last_seen_at,
                    COALESCE(s.browser_metadata_json, '{}') AS browser_metadata_json,
                    CASE WHEN ns.device_id IS NULL OR ns.deleted_at IS NOT NULL THEN 0 ELSE 1 END AS notification_subscription_active,
                    CASE WHEN np.device_id IS NULL THEN 0 ELSE 1 END AS notification_preferences_configured
                   FROM web_app_devices d
                   LEFT JOIN web_app_device_state s ON s.device_id=d.device_id
                   LEFT JOIN web_app_notification_subscriptions ns ON ns.device_id=d.device_id
                   LEFT JOIN web_app_notification_preferences np ON np.device_id=d.device_id
                   WHERE d.device_id=?""",
                (device_id,),
            ).fetchone)
            return dict(row) if row else None

    async def register_passkey(self, *, credential_id: str, core_id: str, user_id: str, device_id: str, public_key: str, sign_count: int) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._conn.execute,
                "INSERT INTO web_app_passkeys VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (credential_id, core_id, user_id, device_id, public_key, sign_count, _now_iso()),
            )

    async def get_passkey(self, device_id: str) -> dict[str, Any] | None:
        async with self._lock:
            row = await asyncio.to_thread(self._conn.execute("SELECT * FROM web_app_passkeys WHERE device_id=?", (device_id,)).fetchone)
            return dict(row) if row else None

    async def update_passkey_counter(self, credential_id: str, sign_count: int) -> None:
        async with self._lock:
            await asyncio.to_thread(self._conn.execute, "UPDATE web_app_passkeys SET sign_count=?, last_used_at=? WHERE credential_id=?", (sign_count, _now_iso(), credential_id))

    async def get_notification_subscription(self, *, device_id: str, core_id: str, user_id: str) -> dict[str, Any] | None:
        async with self._lock:
            row = await asyncio.to_thread(
                self._conn.execute(
                    "SELECT * FROM web_app_notification_subscriptions WHERE device_id=? AND core_id=? AND user_id=? AND deleted_at IS NULL",
                    (device_id, core_id, user_id),
                ).fetchone
            )
            return dict(row) if row else None

    async def list_devices(self, user_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            rows = await asyncio.to_thread(
                self._conn.execute(
                    "SELECT d.*, CASE WHEN d.revoked_at IS NOT NULL THEN 0 ELSE COALESCE(s.enabled, 1) END AS enabled, COALESCE(s.last_seen_at, d.updated_at) AS last_seen_at, COALESCE(s.browser_metadata_json, '{}') AS browser_metadata_json FROM web_app_devices d LEFT JOIN web_app_device_state s ON s.device_id=d.device_id WHERE d.user_id=? ORDER BY d.created_at, d.device_id",
                    (user_id,),
                ).fetchall
            )
            return [dict(row) for row in rows]

    async def list_all_devices(self, core_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            rows = await asyncio.to_thread(
                self._conn.execute(
                    """
                    SELECT d.*,
                      CASE WHEN d.revoked_at IS NOT NULL THEN 0 ELSE COALESCE(ds.enabled, 1) END AS enabled,
                      COALESCE(ds.last_seen_at, d.updated_at) AS last_seen_at,
                      COALESCE(ds.browser_metadata_json, '{}') AS browser_metadata_json,
                      CASE WHEN s.device_id IS NULL OR s.deleted_at IS NOT NULL THEN 0 ELSE 1 END AS notification_subscription_active,
                      s.cleanup_state AS notification_cleanup_state,
                      CASE WHEN p.device_id IS NULL THEN 0 ELSE 1 END AS notification_preferences_configured
                    FROM web_app_devices d
                    LEFT JOIN web_app_notification_subscriptions s ON s.device_id=d.device_id
                    LEFT JOIN web_app_notification_preferences p ON p.device_id=d.device_id
                    LEFT JOIN web_app_device_state ds ON ds.device_id=d.device_id
                    WHERE d.core_id=?
                    ORDER BY d.created_at, d.device_id
                    """,
                    (core_id,),
                ).fetchall
            )
            return [dict(row) for row in rows]

    async def rename_device(self, device_id: str, user_id: str, display_name: str) -> dict[str, Any] | None:
        async with self._lock:
            now = _now_iso()
            changed = await asyncio.to_thread(
                self._conn.execute,
                "UPDATE web_app_devices SET display_name=?, updated_at=? WHERE device_id=? AND user_id=? AND revoked_at IS NULL",
                (display_name, now, device_id, user_id),
            )
            if changed.rowcount != 1:
                return None
            row = await asyncio.to_thread(
                self._conn.execute("SELECT * FROM web_app_devices WHERE device_id=?", (device_id,)).fetchone
            )
            return dict(row) if row else None

    async def set_device_enabled(self, *, device_id: str, core_id: str, enabled: bool) -> dict[str, Any] | None:
        async with self._lock:
            return await asyncio.to_thread(self._set_device_enabled, device_id, core_id, enabled)

    def _set_device_enabled(self, device_id: str, core_id: str, enabled: bool) -> dict[str, Any] | None:
        device = self._conn.execute(
            "SELECT * FROM web_app_devices WHERE device_id=? AND core_id=? AND revoked_at IS NULL",
            (device_id, core_id),
        ).fetchone()
        if device is None:
            return None
        now = _now_iso()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "INSERT INTO web_app_device_state VALUES (?, ?, NULL, '{}', ?) ON CONFLICT(device_id) DO UPDATE SET enabled=excluded.enabled, updated_at=excluded.updated_at",
                (device_id, int(enabled), now),
            )
            if not enabled:
                self._conn.execute(
                    "UPDATE web_app_notification_subscriptions SET deleted_at=COALESCE(deleted_at, ?), updated_at=?, cleanup_state='pending' WHERE device_id=?",
                    (now, now, device_id),
                )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return dict(self._conn.execute(
            "SELECT d.*, s.enabled, COALESCE(s.last_seen_at, d.updated_at) AS last_seen_at, s.browser_metadata_json FROM web_app_devices d JOIN web_app_device_state s ON s.device_id=d.device_id WHERE d.device_id=?",
            (device_id,),
        ).fetchone())

    async def disable_user_devices(self, user_id: str) -> int:
        async with self._lock:
            return await asyncio.to_thread(self._disable_user_devices, user_id)

    def _disable_user_devices(self, user_id: str) -> int:
        rows = self._conn.execute(
            "SELECT device_id FROM web_app_devices WHERE user_id=? AND revoked_at IS NULL",
            (user_id,),
        ).fetchall()
        if not rows:
            return 0
        now = _now_iso()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            for row in rows:
                device_id = str(row["device_id"])
                self._conn.execute(
                    "INSERT INTO web_app_device_state VALUES (?, 0, NULL, '{}', ?) ON CONFLICT(device_id) DO UPDATE SET enabled=0, updated_at=excluded.updated_at",
                    (device_id, now),
                )
                self._conn.execute(
                    "UPDATE web_app_notification_subscriptions SET deleted_at=COALESCE(deleted_at, ?), updated_at=?, cleanup_state='pending' WHERE device_id=?",
                    (now, now, device_id),
                )
            self._conn.execute("COMMIT")
            return len(rows)
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    async def touch_device(self, *, device_id: str, core_id: str, user_id: str) -> bool:
        async with self._lock:
            return await asyncio.to_thread(self._touch_device, device_id, core_id, user_id)

    def _touch_device(self, device_id: str, core_id: str, user_id: str) -> bool:
        device = self._conn.execute(
            "SELECT device_id FROM web_app_devices WHERE device_id=? AND core_id=? AND user_id=? AND revoked_at IS NULL",
            (device_id, core_id, user_id),
        ).fetchone()
        if device is None:
            return False
        now = _now_iso()
        self._conn.execute(
            "INSERT INTO web_app_device_state VALUES (?, 1, ?, '{}', ?) ON CONFLICT(device_id) DO UPDATE SET last_seen_at=excluded.last_seen_at, updated_at=excluded.updated_at WHERE web_app_device_state.enabled=1",
            (device_id, now, now),
        )
        state = self._conn.execute("SELECT enabled FROM web_app_device_state WHERE device_id=?", (device_id,)).fetchone()
        return bool(state and state["enabled"])

    async def revoke_device(self, device_id: str, user_id: str) -> bool:
        async with self._lock:
            now = _now_iso()
            return await asyncio.to_thread(self._revoke_device, device_id, user_id, now)

    def _revoke_device(self, device_id: str, user_id: str, now: str) -> bool:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            changed = self._conn.execute(
                "UPDATE web_app_devices SET revoked_at=?, updated_at=? WHERE device_id=? AND user_id=? AND revoked_at IS NULL",
                (now, now, device_id, user_id),
            )
            if changed.rowcount == 1:
                self._conn.execute("UPDATE web_app_device_state SET enabled=0, updated_at=? WHERE device_id=?", (now, device_id))
                self._conn.execute(
                    "UPDATE web_app_notification_subscriptions SET deleted_at=?, updated_at=?, cleanup_state='pending' WHERE device_id=? AND user_id=? AND deleted_at IS NULL",
                    (now, now, device_id, user_id),
                )
            self._conn.execute("COMMIT")
            return changed.rowcount == 1
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    async def put_notification_subscription(self, *, device_id: str, core_id: str, user_id: str, subscription_ref: str, gateway_audience: str) -> tuple[dict[str, Any], bool]:
        async with self._lock:
            return await asyncio.to_thread(self._put_notification_subscription, device_id, core_id, user_id, subscription_ref, gateway_audience)

    def _put_notification_subscription(self, device_id, core_id, user_id, subscription_ref, gateway_audience):
        device = self._conn.execute(
            "SELECT device_id FROM web_app_devices WHERE device_id=? AND core_id=? AND user_id=? AND revoked_at IS NULL",
            (device_id, core_id, user_id),
        ).fetchone()
        if device is None: raise RuntimeError("device_not_found")
        existing = self._conn.execute("SELECT * FROM web_app_notification_subscriptions WHERE device_id=?", (device_id,)).fetchone()
        if existing is not None and existing["deleted_at"] is None and existing["subscription_ref"] == subscription_ref and existing["gateway_audience"] == gateway_audience:
            return dict(existing), False
        now = _now_iso()
        self._conn.execute(
            "INSERT INTO web_app_notification_subscriptions VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'active') "
            "ON CONFLICT(device_id) DO UPDATE SET core_id=excluded.core_id, user_id=excluded.user_id, subscription_ref=excluded.subscription_ref, gateway_audience=excluded.gateway_audience, updated_at=excluded.updated_at, deleted_at=NULL, cleanup_state='active'",
            (device_id, core_id, user_id, subscription_ref, gateway_audience, now, now),
        )
        return dict(self._conn.execute("SELECT * FROM web_app_notification_subscriptions WHERE device_id=?", (device_id,)).fetchone()), True

    async def delete_notification_subscription(self, *, device_id: str, core_id: str, user_id: str) -> bool:
        async with self._lock:
            now = _now_iso()
            changed = await asyncio.to_thread(
                self._conn.execute,
                "UPDATE web_app_notification_subscriptions SET deleted_at=?, updated_at=?, cleanup_state='pending' WHERE device_id=? AND core_id=? AND user_id=? AND deleted_at IS NULL",
                (now, now, device_id, core_id, user_id),
            )
            return changed.rowcount == 1

    async def pending_notification_cleanup(self, *, core_id: str, limit: int = 100) -> list[dict[str, Any]]:
        async with self._lock:
            rows = await asyncio.to_thread(
                self._conn.execute(
                    "SELECT * FROM web_app_notification_subscriptions WHERE core_id=? AND cleanup_state='pending' ORDER BY updated_at, device_id LIMIT ?",
                    (core_id, max(1, min(limit, 500))),
                ).fetchall
            )
            return [dict(row) for row in rows]

    async def mark_notification_cleanup_complete(self, *, device_id: str, core_id: str, subscription_ref: str) -> bool:
        async with self._lock:
            changed = await asyncio.to_thread(
                self._conn.execute,
                "UPDATE web_app_notification_subscriptions SET cleanup_state='complete', updated_at=? WHERE device_id=? AND core_id=? AND subscription_ref=? AND cleanup_state='pending'",
                (_now_iso(), device_id, core_id, subscription_ref),
            )
            return changed.rowcount == 1

    async def get_notification_preferences(self, *, device_id: str, core_id: str, user_id: str) -> dict[str, Any] | None:
        async with self._lock:
            row = await asyncio.to_thread(
                self._conn.execute(
                    "SELECT * FROM web_app_notification_preferences WHERE device_id=? AND core_id=? AND user_id=?",
                    (device_id, core_id, user_id),
                ).fetchone
            )
            return dict(row) if row else None

    async def list_notification_targets(self, core_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            rows = await asyncio.to_thread(
                self._conn.execute(
                    """
                    SELECT d.device_id, d.user_id, u.role, u.enabled AS user_enabled,
                           ns.subscription_ref, ns.gateway_audience,
                           np.enabled AS preferences_enabled, np.categories_json,
                           np.quiet_hours_start, np.quiet_hours_end, np.time_zone,
                           np.privacy_level, np.severity_threshold
                    FROM web_app_devices d
                    JOIN users u ON u.user_id=d.user_id
                    JOIN web_app_notification_subscriptions ns ON ns.device_id=d.device_id AND ns.deleted_at IS NULL
                    LEFT JOIN web_app_device_state ds ON ds.device_id=d.device_id
                    LEFT JOIN web_app_notification_preferences np ON np.device_id=d.device_id
                    WHERE d.core_id=? AND d.revoked_at IS NULL
                      AND COALESCE(ds.enabled, 1)=1 AND u.enabled=1
                    ORDER BY d.user_id, d.device_id
                    """,
                    (core_id,),
                ).fetchall
            )
            return [dict(row) for row in rows]

    async def put_notification_preferences(self, *, device_id: str, core_id: str, user_id: str, preferences: NotificationPreferencesRequest) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._put_notification_preferences, device_id, core_id, user_id, preferences)

    def _put_notification_preferences(self, device_id, core_id, user_id, preferences):
        device = self._conn.execute(
            "SELECT device_id FROM web_app_devices WHERE device_id=? AND core_id=? AND user_id=? AND revoked_at IS NULL",
            (device_id, core_id, user_id),
        ).fetchone()
        if device is None: raise RuntimeError("device_not_found")
        now = _now_iso()
        self._conn.execute(
            "INSERT INTO web_app_notification_preferences VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(device_id) DO UPDATE SET enabled=excluded.enabled, categories_json=excluded.categories_json, quiet_hours_start=excluded.quiet_hours_start, quiet_hours_end=excluded.quiet_hours_end, time_zone=excluded.time_zone, privacy_level=excluded.privacy_level, severity_threshold=excluded.severity_threshold, updated_at=excluded.updated_at",
            (
                device_id, core_id, user_id, int(preferences.enabled),
                json.dumps(preferences.categories, sort_keys=True, separators=(",", ":")),
                preferences.quiet_hours_start, preferences.quiet_hours_end,
                preferences.time_zone, preferences.privacy_level,
                preferences.severity_threshold, now, now,
            ),
        )
        return dict(self._conn.execute("SELECT * FROM web_app_notification_preferences WHERE device_id=?", (device_id,)).fetchone())

    async def prune_retained_state(self, *, core_id: str, before: str) -> dict[str, int]:
        async with self._lock:
            return await asyncio.to_thread(self._prune_retained_state, core_id, before)

    def _prune_retained_state(self, core_id: str, before: str) -> dict[str, int]:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            removable = """
                SELECT device_id FROM web_app_devices
                WHERE core_id=? AND revoked_at IS NOT NULL AND revoked_at < ?
                  AND NOT EXISTS (
                    SELECT 1 FROM web_app_notification_subscriptions s
                    WHERE s.device_id=web_app_devices.device_id AND s.cleanup_state='pending'
                  )
            """
            preferences = self._conn.execute(
                f"DELETE FROM web_app_notification_preferences WHERE device_id IN ({removable})",
                (core_id, before),
            ).rowcount
            device_state = self._conn.execute(
                f"DELETE FROM web_app_device_state WHERE device_id IN ({removable})",
                (core_id, before),
            ).rowcount
            subscriptions = self._conn.execute(
                "DELETE FROM web_app_notification_subscriptions WHERE core_id=? AND deleted_at IS NOT NULL AND deleted_at < ? AND cleanup_state<>'pending'",
                (core_id, before),
            ).rowcount
            devices = self._conn.execute(
                f"DELETE FROM web_app_devices WHERE device_id IN ({removable})",
                (core_id, before),
            ).rowcount
            enrollments = self._conn.execute(
                """
                DELETE FROM web_app_enrollments
                WHERE core_id=? AND status IN ('consumed','cancelled','expired')
                  AND COALESCE(consumed_at, cancelled_at, expires_at) < ?
                """,
                (core_id, before),
            ).rowcount
            self._conn.execute("COMMIT")
            return {
                "devices": int(devices),
                "notification_preferences": int(preferences),
                "device_state": int(device_state),
                "notification_subscriptions": int(subscriptions),
                "enrollments": int(enrollments),
            }
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    async def rotate_key(self, device_id: str, public_key: str) -> dict[str, Any]:
        async with self._lock:
            await asyncio.to_thread(self._conn.execute, "UPDATE web_app_devices SET public_key=?, updated_at=? WHERE device_id=? AND revoked_at IS NULL", (public_key, _now_iso(), device_id))
            row = await asyncio.to_thread(self._conn.execute("SELECT * FROM web_app_devices WHERE device_id=?", (device_id,)).fetchone)
            if row is None: raise RuntimeError("device_not_found")
            return dict(row)

    async def expire(self, enrollment_id: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._conn.execute, "UPDATE web_app_enrollments SET status='expired' WHERE enrollment_id=? AND status IN ('pending','approved')", (enrollment_id,))


def _verify_signature(public_key: str, signature: str, message: str) -> None:
    try:
        Ed25519PublicKey.from_public_bytes(_decode_b64url(public_key)).verify(_decode_b64url(signature), message.encode("utf-8"))
    except (ValueError, InvalidSignature, TypeError) as exc:
        raise HTTPException(status_code=403, detail="device_key_proof_invalid") from exc


def build_device_enrollment_router(store: WebAppEnrollmentStore, users: UsersStore, keys: ServiceTokenKeyStore, audit: AuditLogStore | None = None, settings: SettingsStore | None = None, assistant_assertions=None) -> APIRouter:
    router = APIRouter()
    notification_gateway_audience = str(os.getenv("HEXE_NOTIFICATION_GATEWAY_AUDIENCE", "hexe-notification-gateway")).strip() or "hexe-notification-gateway"
    retention_days = _env_positive_int("HEXE_WEB_APP_RETENTION_DAYS", 30)

    async def current_identity() -> tuple[str, str]:
        if settings is not None:
            identity = await load_platform_identity(settings)
            return identity.core_id, identity.public_hostname
        core_id = str(os.getenv("HEXE_CORE_ID", "hexe-core")).strip() or "hexe-core"
        platform_domain = str(os.getenv("PLATFORM_DOMAIN", "hexe-ai.com")).strip() or "hexe-ai.com"
        return core_id, f"{core_id}.{platform_domain}"

    async def actor(request: Request, authorization: str | None, admin_token: str | None):
        if authorization:
            principal = await authenticate_human_token(authorization, keys, users)
            principal.require("users.manage")
            return principal.user_id, principal.role
        require_admin_token(admin_token, request)
        actor_id, role = admin_request_actor(request)
        return actor_id, role

    async def record(event, actor_id, role, details):
        if audit: await audit.record(event_type=event, actor_role=role, actor_id=actor_id, details=details)

    def public_device(device: dict[str, Any]) -> dict[str, Any]:
        return {
            "device_id": device["device_id"],
            "display_name": device["display_name"],
            "platform": device.get("platform"),
            "created_at": device["created_at"],
            "updated_at": device["updated_at"],
            "revoked_at": device.get("revoked_at"),
            "enabled": bool(device.get("enabled", not device.get("revoked_at"))),
            "last_seen_at": device.get("last_seen_at"),
            "browser_metadata": json.loads(device.get("browser_metadata_json") or "{}"),
        }

    def public_preferences(preferences: dict[str, Any] | None) -> dict[str, Any]:
        if preferences is None:
            return NotificationPreferencesRequest().model_dump()
        return {
            "enabled": bool(preferences["enabled"]),
            "categories": json.loads(preferences["categories_json"]),
            "quiet_hours_start": preferences.get("quiet_hours_start"),
            "quiet_hours_end": preferences.get("quiet_hours_end"),
            "time_zone": preferences["time_zone"],
            "privacy_level": preferences["privacy_level"],
            "severity_threshold": preferences["severity_threshold"],
        }

    def administrative_device(device: dict[str, Any]) -> dict[str, Any]:
        result = public_device(device)
        result.update(
            {
                "user_id": device["user_id"],
                "core_id": device["core_id"],
                "notification_subscription_active": bool(device.get("notification_subscription_active", False)),
                "notification_cleanup_state": device.get("notification_cleanup_state"),
                "notification_preferences_configured": bool(device.get("notification_preferences_configured", False)),
            }
        )
        return result

    @router.get("/web-app/discovery")
    async def discovery():
        core_id, hostname = await current_identity()
        return {"contract_version": CONTRACT_VERSION, "core_id": core_id, "public_hostname": hostname, "enrollment_supported": True}

    @router.post("/device-enrollments")
    async def create(body: EnrollmentCreateRequest, request: Request, authorization: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
        actor_id, role = await actor(request, authorization, x_admin_token)
        core_id, hostname = await current_identity()
        target_id = body.user_id or actor_id
        if await users.get_user_by_id(target_id) is None: raise HTTPException(status_code=404, detail="user_not_found")
        enrollment, proof = await store.create(core_id=core_id, user_id=target_id, created_by=actor_id, display_name=body.display_name, replace_device_id=body.replace_device_id, ttl_s=body.ttl_seconds)
        await record("web_app_enrollment_created", actor_id, role, {"enrollment_id": enrollment["enrollment_id"], "user_id": target_id})
        return {"ok": True, "enrollment": {"contract_version": CONTRACT_VERSION, "core_id": core_id, "public_hostname": hostname, "enrollment_id": enrollment["enrollment_id"], "expires_at": enrollment["expires_at"], "proof": proof}}

    @router.post("/device-enrollments/{enrollment_id}/approve")
    async def approve(enrollment_id: str, request: Request, authorization: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
        actor_id, role = await actor(request, authorization, x_admin_token)
        try: enrollment = await store.approve(enrollment_id, actor_id)
        except RuntimeError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc
        await record("web_app_enrollment_approved", actor_id, role, {"enrollment_id": enrollment_id, "user_id": enrollment["user_id"]})
        return {"ok": True, "status": enrollment["status"]}

    @router.get("/device-enrollments/{enrollment_id}")
    async def status(enrollment_id: str, request: Request, authorization: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
        await actor(request, authorization, x_admin_token)
        enrollment = await store.get(enrollment_id)
        if enrollment is None: raise HTTPException(status_code=404, detail="enrollment_not_found")
        state = str(enrollment["status"])
        if state in {"pending", "approved"} and datetime.fromisoformat(str(enrollment["expires_at"]).replace("Z", "+00:00")) <= _now():
            state = "expired"
            await store.expire(enrollment_id)
            await record("web_app_enrollment_expired", str(enrollment["created_by"]), "admin", {"enrollment_id": enrollment_id})
        return {"ok": True, "enrollment_id": enrollment_id, "status": state, "expires_at": enrollment["expires_at"], "device_id": enrollment.get("device_id")}

    @router.post("/device-enrollments/{enrollment_id}/passkey-options")
    async def passkey_options(enrollment_id: str, body: EnrollmentPasskeyOptionsRequest):
        enrollment = await store.get(enrollment_id)
        if enrollment is None:
            raise HTTPException(status_code=404, detail="enrollment_not_found")
        if not secrets.compare_digest(str(enrollment["proof_hash"]), _proof_hash(body.proof)):
            raise HTTPException(status_code=403, detail="enrollment_proof_invalid")
        if str(enrollment["status"]) != "approved" or datetime.fromisoformat(str(enrollment["expires_at"]).replace("Z", "+00:00")) <= _now():
            raise HTTPException(status_code=409, detail="enrollment_not_approved")
        user = await users.get_user_by_id(str(enrollment["user_id"]))
        core_id, hostname = await current_identity()
        if user is None or str(enrollment["core_id"]) != core_id:
            raise HTTPException(status_code=403, detail="enrollment_identity_invalid")
        return {
            "challenge": enrollment["challenge"],
            "rp": {"id": hostname, "name": "Hexe Core"},
            "user": {"id": _encode_b64url(str(user["user_id"]).encode()), "name": user["username"], "displayName": user["username"]},
            "timeout": 120000,
            "attestation": "none",
            "authenticatorSelection": {"authenticatorAttachment": "platform", "residentKey": "required", "userVerification": "required"},
            "pubKeyCredParams": [{"type": "public-key", "alg": -7}, {"type": "public-key", "alg": -8}],
        }

    @router.post("/device-enrollments/{enrollment_id}/complete")
    async def complete(enrollment_id: str, body: EnrollmentCompleteRequest):
        enrollment = await store.get(enrollment_id)
        if enrollment is None: raise HTTPException(status_code=404, detail="enrollment_not_found")
        core_id, hostname = await current_identity()
        if str(enrollment["core_id"]) != core_id:
            raise HTTPException(status_code=403, detail="enrollment_core_mismatch")
        try:
            verified_passkey = verify_registration_response(
                credential=body.passkey_credential,
                expected_challenge=_decode_b64url(str(enrollment["challenge"])),
                expected_rp_id=hostname,
                expected_origin=f"https://{hostname}",
                require_user_verification=True,
            )
        except (InvalidRegistrationResponse, ValueError, TypeError) as exc:
            raise HTTPException(status_code=403, detail="passkey_registration_invalid") from exc
        message = f"{CONTRACT_VERSION}:{enrollment['core_id']}:{enrollment_id}:{body.device_id}"
        try:
            _verify_signature(body.public_key, body.signature, message)
            consumed = await store.consume(
                enrollment_id=enrollment_id, proof=body.proof, device_id=body.device_id,
                public_key=body.public_key, platform=body.platform, browser_metadata=body.browser_metadata,
                passkey={"credential_id": _encode_b64url(verified_passkey.credential_id), "public_key": _encode_b64url(verified_passkey.credential_public_key), "sign_count": verified_passkey.sign_count},
            )
        except HTTPException:
            await record("web_app_enrollment_failed", "anonymous", "guest", {"enrollment_id": enrollment_id, "reason": "device_key_proof_invalid"})
            raise
        except RuntimeError as exc:
            await record("web_app_enrollment_failed", "anonymous", "guest", {"enrollment_id": enrollment_id, "reason": str(exc)})
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        user = await users.get_user_by_id(str(consumed["user_id"]))
        if user is None: raise HTTPException(status_code=409, detail="user_not_available")
        if consumed.get("replace_device_id"):
            await users.revoke_device_sessions(str(consumed["replace_device_id"]), reason="device_recovered")
        refresh = secrets.token_urlsafe(48)
        session = await users.create_session(user_id=str(user["user_id"]), device_id=body.device_id, refresh_verifier=_refresh_verifier(refresh), expires_at=_iso_after(30 * 24 * 60 * 60))
        access, claims = await _access_token(keys, user, session)
        await record("web_app_enrollment_completed", str(user["user_id"]), str(user["role"]), {"enrollment_id": enrollment_id, "device_id": body.device_id, "session_id": session["session_id"]})
        return {"ok": True, "device_id": body.device_id, "access_token": access, "refresh_token": refresh, "token_type": "bearer", "expires_in": 600, "claims": claims}

    @router.post("/user/device-login/challenge")
    async def device_login_challenge(body: DeviceLoginChallengeRequest):
        device = await store.get_device(body.device_id)
        user = await users.get_user_by_id(str(device["user_id"])) if device is not None else None
        passkey = await store.get_passkey(body.device_id)
        core_id, _ = await current_identity()
        if user is None or device is None or not bool(user.get("enabled")) or str(device.get("user_id")) != str(user.get("user_id")) or str(device.get("core_id")) != core_id or device.get("revoked_at") or not bool(device.get("enabled", True)):
            await record("web_app_device_login_failed", "anonymous", "guest", {"reason": "invalid_credentials_or_device"})
            raise HTTPException(status_code=401, detail="invalid_credentials_or_device")
        if passkey is None:
            verified_user = await users.verify_credentials(body.username or "", body.password or "")
            if verified_user is None or str(verified_user["user_id"]) != str(user["user_id"]):
                raise HTTPException(status_code=401, detail="passkey_upgrade_requires_password")
        challenge = await store.create_login_challenge(core_id=core_id, user_id=str(user["user_id"]), device_id=body.device_id)
        await record("web_app_device_login_challenged", str(user["user_id"]), str(user["role"]), {"device_id": body.device_id, "challenge_id": challenge["challenge_id"]})
        response = {"ok": True, "contract_version": DEVICE_LOGIN_VERSION, **challenge}
        if passkey is not None:
            return {**response, "credential_id": passkey["credential_id"]}
        _, hostname = await current_identity()
        return {**response, "passkey_registration_required": True, "registration_options": {
            "challenge": challenge["nonce"], "rp": {"id": hostname, "name": "Hexe Core"},
            "user": {"id": _encode_b64url(str(user["user_id"]).encode()), "name": user["username"], "displayName": user["username"]},
            "timeout": 120000, "attestation": "none",
            "authenticatorSelection": {"authenticatorAttachment": "platform", "residentKey": "required", "userVerification": "required"},
            "pubKeyCredParams": [{"type": "public-key", "alg": -7}, {"type": "public-key", "alg": -8}],
        }}

    @router.post("/user/device-login/complete")
    async def device_login_complete(body: DeviceLoginCompleteRequest):
        try:
            challenge = await store.consume_login_challenge(body.challenge_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        device = await store.get_device(str(challenge["device_id"]))
        passkey = await store.get_passkey(str(challenge["device_id"]))
        user = await users.get_user_by_id(str(challenge["user_id"]))
        core_id, hostname = await current_identity()
        if device is None or user is None or not bool(user.get("enabled")) or device.get("revoked_at") or not bool(device.get("enabled", True)) or str(device.get("core_id")) != core_id or str(device.get("user_id")) != str(user.get("user_id")):
            raise HTTPException(status_code=403, detail="enrolled_device_invalid")
        message = f"{DEVICE_LOGIN_VERSION}:{challenge['core_id']}:{challenge['challenge_id']}:{challenge['nonce']}:{challenge['device_id']}"
        _verify_signature(str(device["public_key"]), body.signature, message)
        try:
            if passkey is None:
                registered = verify_registration_response(
                    credential=body.passkey_credential, expected_challenge=_decode_b64url(str(challenge["nonce"])),
                    expected_rp_id=hostname, expected_origin=f"https://{hostname}", require_user_verification=True,
                )
                await store.register_passkey(credential_id=_encode_b64url(registered.credential_id), core_id=core_id, user_id=str(user["user_id"]), device_id=str(device["device_id"]), public_key=_encode_b64url(registered.credential_public_key), sign_count=registered.sign_count)
            else:
                verified_passkey = verify_authentication_response(
                credential=body.passkey_credential,
                expected_challenge=_decode_b64url(str(challenge["nonce"])),
                expected_rp_id=hostname,
                expected_origin=f"https://{hostname}",
                credential_public_key=_decode_b64url(str(passkey["public_key"])),
                credential_current_sign_count=int(passkey["sign_count"]),
                require_user_verification=True,
                )
                if _encode_b64url(verified_passkey.credential_id) != str(passkey["credential_id"]):
                    raise HTTPException(status_code=403, detail="passkey_credential_mismatch")
                await store.update_passkey_counter(str(passkey["credential_id"]), verified_passkey.new_sign_count)
        except (InvalidAuthenticationResponse, InvalidRegistrationResponse, ValueError, TypeError) as exc:
            raise HTTPException(status_code=403, detail="passkey_verification_invalid") from exc
        refresh = secrets.token_urlsafe(48)
        session = await users.create_session(user_id=str(user["user_id"]), device_id=str(device["device_id"]), refresh_verifier=_refresh_verifier(refresh), expires_at=_iso_after(30 * 24 * 60 * 60))
        access, claims = await _access_token(keys, user, session)
        await record("web_app_device_login_succeeded", str(user["user_id"]), str(user["role"]), {"device_id": device["device_id"], "session_id": session["session_id"]})
        return {"ok": True, "access_token": access, "refresh_token": refresh, "token_type": "bearer", "expires_in": 600, "claims": claims}

    @router.post("/device-enrollments/{enrollment_id}/cancel")
    async def cancel(enrollment_id: str, request: Request, authorization: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
        actor_id, role = await actor(request, authorization, x_admin_token)
        try: enrollment = await store.cancel(enrollment_id)
        except RuntimeError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc
        await record("web_app_enrollment_cancelled", actor_id, role, {"enrollment_id": enrollment_id})
        return {"ok": True, "status": enrollment["status"]}

    @router.post("/devices/{device_id}/rotate-key")
    async def rotate_key(device_id: str, body: DeviceKeyRotationRequest, authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        if principal.device_id != device_id: raise HTTPException(status_code=403, detail="device_identity_mismatch")
        device = await store.get_device(device_id)
        if device is None or device.get("revoked_at") or str(device["user_id"]) != principal.user_id: raise HTTPException(status_code=404, detail="device_not_found")
        message = f"{CONTRACT_VERSION}:rotate:{device['core_id']}:{device_id}:{body.new_public_key}"
        _verify_signature(str(device["public_key"]), body.old_key_signature, message)
        _verify_signature(body.new_public_key, body.new_key_signature, message)
        await store.rotate_key(device_id, body.new_public_key)
        await record("web_app_device_key_rotated", principal.user_id, principal.role, {"device_id": device_id})
        return {"ok": True, "device_id": device_id}

    @router.get("/devices")
    async def list_devices(authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        items = [public_device(device) for device in await store.list_devices(principal.user_id)]
        return {"ok": True, "items": items, "current_device_id": principal.device_id}

    @router.get("/devices/admin")
    async def list_all_devices(authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        principal.require("users.manage")
        core_id, _ = await current_identity()
        items = [administrative_device(device) for device in await store.list_all_devices(core_id)]
        return {"ok": True, "items": items}

    @router.delete("/devices/admin/{device_id}")
    async def administratively_revoke_device(device_id: str, authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        principal.require("users.manage")
        device = await store.get_device(device_id)
        core_id, _ = await current_identity()
        if device is None or device.get("revoked_at") or str(device["core_id"]) != core_id:
            raise HTTPException(status_code=404, detail="device_not_found")
        target_user = await users.get_user_by_id(str(device["user_id"]))
        if target_user is not None and str(target_user.get("role")) == "owner" and principal.role != "owner":
            raise HTTPException(status_code=403, detail="owner_role_required")
        if not await store.revoke_device(device_id, str(device["user_id"])):
            raise HTTPException(status_code=404, detail="device_not_found")
        await users.revoke_device_sessions(device_id, reason="administrator_revoked_device")
        if assistant_assertions is not None:
            await assistant_assertions.bump_authorization_epoch(kind="device", identifier=device_id)
        await record(
            "web_app_device_administrator_revoked",
            principal.user_id,
            principal.role,
            {"device_id": device_id, "target_user_id": device["user_id"]},
        )
        return {"ok": True, "device_id": device_id}

    @router.post("/devices/admin/prune")
    async def prune_retained_device_state(authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        principal.require("users.manage")
        core_id, _ = await current_identity()
        before = (_now() - timedelta(days=retention_days)).isoformat()
        device_counts = await store.prune_retained_state(core_id=core_id, before=before)
        session_counts = await users.prune_sessions(before)
        counts = device_counts | session_counts
        await record(
            "web_app_retained_state_pruned",
            principal.user_id,
            principal.role,
            {"retention_days": retention_days, "counts": counts},
        )
        return {"ok": True, "retention_days": retention_days, "before": before, "counts": counts}

    @router.patch("/devices/admin/{device_id}/state")
    async def update_device_state(device_id: str, body: DeviceStateUpdateRequest, authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        principal.require("users.manage")
        device = await store.get_device(device_id)
        core_id, _ = await current_identity()
        if device is None or device.get("revoked_at") or str(device["core_id"]) != core_id:
            raise HTTPException(status_code=404, detail="device_not_found")
        target_user = await users.get_user_by_id(str(device["user_id"]))
        if target_user is not None and str(target_user.get("role")) == "owner" and principal.role != "owner":
            raise HTTPException(status_code=403, detail="owner_role_required")
        updated = await store.set_device_enabled(device_id=device_id, core_id=core_id, enabled=body.enabled)
        if updated is None:
            raise HTTPException(status_code=404, detail="device_not_found")
        if not body.enabled:
            await users.revoke_device_sessions(device_id, reason="administrator_disabled_device")
            if assistant_assertions is not None:
                await assistant_assertions.bump_authorization_epoch(kind="device", identifier=device_id)
        await record(
            "web_app_device_enabled_changed",
            principal.user_id,
            principal.role,
            {"device_id": device_id, "target_user_id": device["user_id"], "enabled": body.enabled},
        )
        return {"ok": True, "device": administrative_device(updated)}

    @router.patch("/devices/{device_id}")
    async def rename_device(device_id: str, body: DeviceUpdateRequest, authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        device = await store.rename_device(device_id, principal.user_id, body.display_name.strip())
        if device is None:
            raise HTTPException(status_code=404, detail="device_not_found")
        await record("web_app_device_renamed", principal.user_id, principal.role, {"device_id": device_id})
        return {"ok": True, "device": public_device(device)}

    @router.delete("/devices/{device_id}")
    async def revoke_device(device_id: str, authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        if not await store.revoke_device(device_id, principal.user_id):
            raise HTTPException(status_code=404, detail="device_not_found")
        await users.revoke_device_sessions(device_id, reason="device_revoked")
        if assistant_assertions is not None:
            await assistant_assertions.bump_authorization_epoch(kind="device", identifier=device_id)
        await record("web_app_device_revoked", principal.user_id, principal.role, {"device_id": device_id})
        return {"ok": True, "device_id": device_id}

    @router.put("/devices/{device_id}/notification-subscription")
    async def put_notification_subscription(device_id: str, body: NotificationSubscriptionRequest, authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        if principal.device_id != device_id:
            raise HTTPException(status_code=403, detail="device_identity_mismatch")
        if body.gateway_audience != notification_gateway_audience:
            raise HTTPException(status_code=409, detail="notification_gateway_audience_mismatch")
        core_id, _ = await current_identity()
        try:
            subscription, changed = await store.put_notification_subscription(
                device_id=device_id,
                core_id=core_id,
                user_id=principal.user_id,
                subscription_ref=body.subscription_ref,
                gateway_audience=body.gateway_audience,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await record(
            "web_app_notification_subscription_registered",
            principal.user_id,
            principal.role,
            {"device_id": device_id, "changed": changed},
        )
        return {
            "ok": True,
            "device_id": device_id,
            "gateway_audience": subscription["gateway_audience"],
            "updated_at": subscription["updated_at"],
            "changed": changed,
        }

    @router.delete("/devices/{device_id}/notification-subscription")
    async def delete_notification_subscription(device_id: str, authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        if principal.device_id != device_id:
            raise HTTPException(status_code=403, detail="device_identity_mismatch")
        core_id, _ = await current_identity()
        changed = await store.delete_notification_subscription(device_id=device_id, core_id=core_id, user_id=principal.user_id)
        await record(
            "web_app_notification_subscription_deleted",
            principal.user_id,
            principal.role,
            {"device_id": device_id, "changed": changed},
        )
        return {"ok": True, "device_id": device_id, "changed": changed, "cleanup_state": "pending" if changed else "absent"}

    @router.get("/devices/{device_id}/notification-preferences")
    async def get_notification_preferences(device_id: str, authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        if principal.device_id != device_id:
            raise HTTPException(status_code=403, detail="device_identity_mismatch")
        device = await store.get_device(device_id)
        core_id, _ = await current_identity()
        if device is None or device.get("revoked_at") or str(device["core_id"]) != core_id or str(device["user_id"]) != principal.user_id:
            raise HTTPException(status_code=404, detail="device_not_found")
        preferences = await store.get_notification_preferences(device_id=device_id, core_id=core_id, user_id=principal.user_id)
        return {"ok": True, "device_id": device_id, "preferences": public_preferences(preferences)}

    @router.put("/devices/{device_id}/notification-preferences")
    async def put_notification_preferences(device_id: str, body: NotificationPreferencesRequest, authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        if principal.device_id != device_id:
            raise HTTPException(status_code=403, detail="device_identity_mismatch")
        core_id, _ = await current_identity()
        try:
            preferences = await store.put_notification_preferences(
                device_id=device_id,
                core_id=core_id,
                user_id=principal.user_id,
                preferences=body,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await record("web_app_notification_preferences_updated", principal.user_id, principal.role, {"device_id": device_id})
        return {"ok": True, "device_id": device_id, "preferences": public_preferences(preferences)}

    return router
