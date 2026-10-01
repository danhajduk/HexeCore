from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.admin import admin_request_actor, require_admin_token
from app.system.audit import AuditLogStore
from app.system.users.store import UsersStore
from .human import _access_token, _iso_after, _refresh_verifier, authenticate_human_token
from .tokens import ServiceTokenKeyStore

CONTRACT_VERSION = "hexe.web-app-enrollment.v1"
DEFAULT_TTL_S = 10 * 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _decode_b64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


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


class DeviceKeyRotationRequest(BaseModel):
    new_public_key: str = Field(..., min_length=43, max_length=128)
    old_key_signature: str = Field(..., min_length=43, max_length=256)
    new_key_signature: str = Field(..., min_length=43, max_length=256)


class WebAppEnrollmentStore:
    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
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
            """
        )

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

    async def consume(self, *, enrollment_id: str, proof: str, device_id: str, public_key: str, platform: str | None) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._consume, enrollment_id, proof, device_id, public_key, platform)

    def _consume(self, enrollment_id, proof, device_id, public_key, platform):
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
            if replace_id:
                replacement = self._conn.execute("SELECT * FROM web_app_devices WHERE device_id=? AND user_id=? AND revoked_at IS NULL", (replace_id, row["user_id"])).fetchone()
                if replacement is None: raise RuntimeError("replacement_device_not_available")
                self._conn.execute("UPDATE web_app_devices SET revoked_at=?, updated_at=? WHERE device_id=?", (_now_iso(), _now_iso(), replace_id))
            now = _now_iso()
            self._conn.execute("INSERT INTO web_app_devices VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL) ON CONFLICT(device_id) DO UPDATE SET public_key=excluded.public_key, platform=excluded.platform, updated_at=excluded.updated_at, revoked_at=NULL", (device_id, row["core_id"], row["user_id"], row["display_name"], public_key, platform, now, now))
            changed = self._conn.execute("UPDATE web_app_enrollments SET status='consumed', consumed_at=?, device_id=? WHERE enrollment_id=? AND status='approved'", (now, device_id, enrollment_id)).rowcount
            if changed != 1: raise RuntimeError("enrollment_already_consumed")
            self._conn.execute("COMMIT")
            return self._get(enrollment_id)
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    async def get_device(self, device_id: str) -> dict[str, Any] | None:
        async with self._lock:
            row = await asyncio.to_thread(self._conn.execute("SELECT * FROM web_app_devices WHERE device_id=?", (device_id,)).fetchone)
            return dict(row) if row else None

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


def build_device_enrollment_router(store: WebAppEnrollmentStore, users: UsersStore, keys: ServiceTokenKeyStore, audit: AuditLogStore | None = None) -> APIRouter:
    router = APIRouter()
    core_id = str(os.getenv("HEXE_CORE_ID", "hexe-core")).strip() or "hexe-core"
    platform_domain = str(os.getenv("PLATFORM_DOMAIN", "hexe-ai.com")).strip() or "hexe-ai.com"
    hostname = f"{core_id}.{platform_domain}"

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

    @router.get("/web-app/discovery")
    async def discovery():
        return {"contract_version": CONTRACT_VERSION, "core_id": core_id, "public_hostname": hostname, "enrollment_supported": True}

    @router.post("/device-enrollments")
    async def create(body: EnrollmentCreateRequest, request: Request, authorization: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
        actor_id, role = await actor(request, authorization, x_admin_token)
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

    @router.post("/device-enrollments/{enrollment_id}/complete")
    async def complete(enrollment_id: str, body: EnrollmentCompleteRequest):
        enrollment = await store.get(enrollment_id)
        if enrollment is None: raise HTTPException(status_code=404, detail="enrollment_not_found")
        message = f"{CONTRACT_VERSION}:{core_id}:{enrollment_id}:{body.device_id}"
        try:
            _verify_signature(body.public_key, body.signature, message)
            consumed = await store.consume(enrollment_id=enrollment_id, proof=body.proof, device_id=body.device_id, public_key=body.public_key, platform=body.platform)
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
        message = f"{CONTRACT_VERSION}:rotate:{core_id}:{device_id}:{body.new_public_key}"
        _verify_signature(str(device["public_key"]), body.old_key_signature, message)
        _verify_signature(body.new_public_key, body.new_key_signature, message)
        await store.rotate_key(device_id, body.new_public_key)
        await record("web_app_device_key_rotated", principal.user_id, principal.role, {"device_id": device_id})
        return {"ok": True, "device_id": device_id}

    return router
