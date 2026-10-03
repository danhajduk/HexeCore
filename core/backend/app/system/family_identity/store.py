from __future__ import annotations

import asyncio
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FamilyIdentityError(RuntimeError):
    pass


class FamilyIdentityStore:
    """Core-owned person and household state. Login accounts remain in UsersStore."""

    def __init__(self, path: str, core_id: str) -> None:
        self.path = path
        self.core_id = core_id
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()
        self._init()

    def _init(self) -> None:
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS family_households (
          household_id TEXT PRIMARY KEY, core_id TEXT NOT NULL, display_name TEXT NOT NULL,
          status TEXT NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS family_people (
          person_id TEXT PRIMARY KEY, core_id TEXT NOT NULL, household_id TEXT NOT NULL,
          display_name TEXT NOT NULL, age_band TEXT, status TEXT NOT NULL, version INTEGER NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, archived_at TEXT);
        CREATE TABLE IF NOT EXISTS family_user_links (
          person_id TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE, core_id TEXT NOT NULL,
          linked_at TEXT NOT NULL, linked_by TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS family_guardians (
          relationship_id TEXT PRIMARY KEY, core_id TEXT NOT NULL, household_id TEXT NOT NULL,
          guardian_person_id TEXT NOT NULL, dependent_person_id TEXT NOT NULL, purposes_json TEXT NOT NULL,
          operations_json TEXT NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL,
          effective_at TEXT NOT NULL, expires_at TEXT, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS family_consents (
          consent_id TEXT PRIMARY KEY, core_id TEXT NOT NULL, household_id TEXT NOT NULL,
          person_id TEXT NOT NULL, purpose TEXT NOT NULL, decision TEXT NOT NULL,
          visibility_json TEXT NOT NULL, actor_person_id TEXT, policy_version TEXT NOT NULL,
          status TEXT NOT NULL, version INTEGER NOT NULL, decided_at TEXT NOT NULL,
          expires_at TEXT, revoked_at TEXT, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS family_rooms (
          room_id TEXT PRIMARY KEY, core_id TEXT NOT NULL, household_id TEXT NOT NULL,
          display_name TEXT NOT NULL, audience_mode TEXT NOT NULL, status TEXT NOT NULL,
          version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS family_endpoint_assignments (
          endpoint_id TEXT PRIMARY KEY, core_id TEXT NOT NULL, household_id TEXT NOT NULL,
          room_id TEXT NOT NULL, version INTEGER NOT NULL, assigned_at TEXT NOT NULL, assigned_by TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS family_lifecycle_requests (
          request_id TEXT PRIMARY KEY, core_id TEXT NOT NULL, person_id TEXT NOT NULL,
          kind TEXT NOT NULL, state TEXT NOT NULL, requested_by TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, receipts_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS family_authorization_replay (
          jti TEXT PRIMARY KEY, expires_at TEXT NOT NULL);
        """)
        self._conn.commit()

    async def _run(self, fn, *args):
        async with self._lock:
            return await asyncio.to_thread(fn, *args)

    async def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return await self._run(self._snapshot)

    async def self_view(self, user_id: str) -> dict[str, Any]:
        return await self._run(self._self_view, user_id)

    def _self_view(self, user_id: str) -> dict[str, Any]:
        link = self._conn.execute("SELECT * FROM family_user_links WHERE user_id=? AND core_id=?", (user_id, self.core_id)).fetchone()
        if link is None:
            return {"linked": False, "person": None, "consents": [], "guardian_authority": []}
        person_id = str(link["person_id"])
        person = self._person(person_id, active=False)
        consents = [row for row in self._rows("family_consents") if row["person_id"] == person_id]
        guardians = [row for row in self._rows("family_guardians") if row["guardian_person_id"] == person_id or row["dependent_person_id"] == person_id]
        return {"linked": True, "person": dict(person), "consents": consents, "guardian_authority": guardians}

    def _rows(self, table: str) -> list[dict[str, Any]]:
        rows = [dict(row) for row in self._conn.execute(f"SELECT * FROM {table} WHERE core_id = ? ORDER BY created_at" if table in {"family_households", "family_people", "family_rooms", "family_lifecycle_requests"} else f"SELECT * FROM {table} WHERE core_id = ?", (self.core_id,)).fetchall()]
        for row in rows:
            for key in tuple(row):
                if key.endswith("_json"):
                    row[key[:-5]] = json.loads(row.pop(key) or "[]")
        return rows

    def _snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "households": self._rows("family_households"), "people": self._rows("family_people"),
            "user_links": self._rows("family_user_links"), "guardians": self._rows("family_guardians"),
            "consents": self._rows("family_consents"), "rooms": self._rows("family_rooms"),
            "endpoint_assignments": self._rows("family_endpoint_assignments"),
            "lifecycle_requests": self._rows("family_lifecycle_requests"),
        }

    async def create_household(self, display_name: str) -> dict[str, Any]:
        return await self._run(self._create_household, display_name)

    def _create_household(self, display_name: str) -> dict[str, Any]:
        name = display_name.strip()
        if not name:
            raise FamilyIdentityError("display_name_required")
        now, identifier = _now(), f"hh_{secrets.token_urlsafe(16)}"
        self._conn.execute("INSERT INTO family_households VALUES (?,?,?,'active',1,?,?)", (identifier, self.core_id, name, now, now))
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM family_households WHERE household_id=?", (identifier,)).fetchone())

    async def create_person(self, household_id: str, display_name: str, age_band: str | None) -> dict[str, Any]:
        return await self._run(self._create_person, household_id, display_name, age_band)

    def _household(self, household_id: str) -> sqlite3.Row:
        row = self._conn.execute("SELECT * FROM family_households WHERE household_id=? AND core_id=? AND status='active'", (household_id, self.core_id)).fetchone()
        if row is None:
            raise FamilyIdentityError("household_not_found")
        return row

    def _person(self, person_id: str, *, active: bool = True) -> sqlite3.Row:
        suffix = " AND status='active'" if active else ""
        row = self._conn.execute(f"SELECT * FROM family_people WHERE person_id=? AND core_id=?{suffix}", (person_id, self.core_id)).fetchone()
        if row is None:
            raise FamilyIdentityError("person_not_found")
        return row

    def _create_person(self, household_id: str, display_name: str, age_band: str | None) -> dict[str, Any]:
        self._household(household_id)
        name = display_name.strip()
        if not name:
            raise FamilyIdentityError("display_name_required")
        if age_band not in {None, "adult", "teen", "child", "unknown"}:
            raise FamilyIdentityError("age_band_invalid")
        now, identifier = _now(), f"per_{secrets.token_urlsafe(16)}"
        self._conn.execute("INSERT INTO family_people VALUES (?,?,?,?,?,'active',1,?,?,NULL)", (identifier, self.core_id, household_id, name, age_band, now, now))
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM family_people WHERE person_id=?", (identifier,)).fetchone())

    async def update_person(self, person_id: str, display_name: str, age_band: str | None, expected_version: int, archive: bool) -> dict[str, Any]:
        return await self._run(self._update_person, person_id, display_name, age_band, expected_version, archive)

    def _update_person(self, person_id: str, display_name: str, age_band: str | None, expected_version: int, archive: bool) -> dict[str, Any]:
        row = self._person(person_id, active=False)
        if int(row["version"]) != expected_version:
            raise FamilyIdentityError("version_conflict")
        name = display_name.strip()
        if not name or age_band not in {None, "adult", "teen", "child", "unknown"}:
            raise FamilyIdentityError("person_invalid")
        now = _now()
        self._conn.execute("UPDATE family_people SET display_name=?,age_band=?,status=?,version=version+1,updated_at=?,archived_at=? WHERE person_id=?", (name, age_band, "archived" if archive else "active", now, now if archive else None, person_id))
        if archive:
            self._conn.execute("DELETE FROM family_user_links WHERE person_id=?", (person_id,))
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM family_people WHERE person_id=?", (person_id,)).fetchone())

    async def link_user(self, person_id: str, user_id: str, actor_id: str) -> dict[str, Any]:
        return await self._run(self._link_user, person_id, user_id, actor_id)

    def _link_user(self, person_id: str, user_id: str, actor_id: str) -> dict[str, Any]:
        self._person(person_id)
        try:
            self._conn.execute("INSERT INTO family_user_links VALUES (?,?,?,?,?)", (person_id, user_id, self.core_id, _now(), actor_id))
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise FamilyIdentityError("user_or_person_already_linked") from exc
        return dict(self._conn.execute("SELECT * FROM family_user_links WHERE person_id=?", (person_id,)).fetchone())

    async def unlink_user(self, person_id: str) -> bool:
        return await self._run(self._unlink_user, person_id)

    def _unlink_user(self, person_id: str) -> bool:
        changed = self._conn.execute("DELETE FROM family_user_links WHERE person_id=? AND core_id=?", (person_id, self.core_id)).rowcount
        self._conn.commit()
        return bool(changed)

    async def create_guardian(self, guardian_id: str, dependent_id: str, purposes: list[str], operations: list[str], expires_at: str | None) -> dict[str, Any]:
        return await self._run(self._create_guardian, guardian_id, dependent_id, purposes, operations, expires_at)

    def _create_guardian(self, guardian_id: str, dependent_id: str, purposes: list[str], operations: list[str], expires_at: str | None) -> dict[str, Any]:
        guardian, dependent = self._person(guardian_id), self._person(dependent_id)
        if guardian_id == dependent_id or guardian["household_id"] != dependent["household_id"]:
            raise FamilyIdentityError("guardian_scope_invalid")
        now, identifier = _now(), f"rel_{secrets.token_urlsafe(16)}"
        self._conn.execute("INSERT INTO family_guardians VALUES (?,?,?,?,?,?,?,'active',1,?,?,?)", (identifier, self.core_id, guardian["household_id"], guardian_id, dependent_id, json.dumps(sorted(set(purposes))), json.dumps(sorted(set(operations))), now, expires_at, now))
        self._conn.commit()
        return self._rows("family_guardians")[-1]

    async def create_consent(self, person_id: str, purpose: str, decision: str, visibility: list[str], actor_person_id: str | None, expires_at: str | None) -> dict[str, Any]:
        return await self._run(self._create_consent, person_id, purpose, decision, visibility, actor_person_id, expires_at)

    def _create_consent(self, person_id: str, purpose: str, decision: str, visibility: list[str], actor_person_id: str | None, expires_at: str | None) -> dict[str, Any]:
        person = self._person(person_id)
        if purpose not in {"memory.read", "memory.write", "personalization", "speaker-recognition", "model-training", "export"} or decision not in {"granted", "denied"}:
            raise FamilyIdentityError("consent_invalid")
        now, identifier = _now(), f"con_{secrets.token_urlsafe(16)}"
        self._conn.execute(
            "INSERT INTO family_consents (consent_id,core_id,household_id,person_id,purpose,decision,visibility_json,actor_person_id,policy_version,status,version,decided_at,expires_at,revoked_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,'active',1,?,?,NULL,?)",
            (identifier, self.core_id, person["household_id"], person_id, purpose, decision, json.dumps(sorted(set(visibility))), actor_person_id, "v1", now, expires_at, now),
        )
        self._conn.commit()
        return self._rows("family_consents")[-1]

    async def create_room(self, household_id: str, display_name: str, audience_mode: str) -> dict[str, Any]:
        return await self._run(self._create_room, household_id, display_name, audience_mode)

    def _create_room(self, household_id: str, display_name: str, audience_mode: str) -> dict[str, Any]:
        self._household(household_id)
        if audience_mode not in {"private", "household", "room"} or not display_name.strip():
            raise FamilyIdentityError("room_invalid")
        now, identifier = _now(), f"room_{secrets.token_urlsafe(16)}"
        self._conn.execute("INSERT INTO family_rooms VALUES (?,?,?,?,?,'active',1,?,?)", (identifier, self.core_id, household_id, display_name.strip(), audience_mode, now, now))
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM family_rooms WHERE room_id=?", (identifier,)).fetchone())

    async def assign_endpoint(self, endpoint_id: str, room_id: str, actor_id: str) -> dict[str, Any]:
        return await self._run(self._assign_endpoint, endpoint_id, room_id, actor_id)

    def _assign_endpoint(self, endpoint_id: str, room_id: str, actor_id: str) -> dict[str, Any]:
        room = self._conn.execute("SELECT * FROM family_rooms WHERE room_id=? AND core_id=? AND status='active'", (room_id, self.core_id)).fetchone()
        if room is None or not endpoint_id.strip():
            raise FamilyIdentityError("room_or_endpoint_invalid")
        existing = self._conn.execute("SELECT version FROM family_endpoint_assignments WHERE endpoint_id=?", (endpoint_id,)).fetchone()
        version = int(existing["version"]) + 1 if existing else 1
        self._conn.execute("INSERT INTO family_endpoint_assignments VALUES (?,?,?,?,?,?,?) ON CONFLICT(endpoint_id) DO UPDATE SET household_id=excluded.household_id,room_id=excluded.room_id,version=excluded.version,assigned_at=excluded.assigned_at,assigned_by=excluded.assigned_by", (endpoint_id, self.core_id, room["household_id"], room_id, version, _now(), actor_id))
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM family_endpoint_assignments WHERE endpoint_id=?", (endpoint_id,)).fetchone())

    async def request_lifecycle(self, person_id: str, kind: str, actor_id: str) -> dict[str, Any]:
        return await self._run(self._request_lifecycle, person_id, kind, actor_id)

    def _request_lifecycle(self, person_id: str, kind: str, actor_id: str) -> dict[str, Any]:
        self._person(person_id, active=False)
        if kind not in {"export", "delete"}:
            raise FamilyIdentityError("lifecycle_kind_invalid")
        now, identifier = _now(), f"life_{secrets.token_urlsafe(16)}"
        self._conn.execute("INSERT INTO family_lifecycle_requests VALUES (?,?,?,?,?,?,?,?,'[]')", (identifier, self.core_id, person_id, kind, "incomplete", actor_id, now, now))
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM family_lifecycle_requests WHERE request_id=?", (identifier,)).fetchone())

    async def authorization_context(self, *, user_id: str, session_id: str, device_id: str | None, household_id: str, operation: str, risk: str, visibility: list[str], identity_state: str = "authenticated", room_id: str | None = None, endpoint_id: str | None = None) -> dict[str, Any]:
        return await self._run(self._authorization_context, user_id, session_id, device_id, household_id, operation, risk, visibility, identity_state, room_id, endpoint_id)

    def _authorization_context(self, user_id: str, session_id: str, device_id: str | None, household_id: str, operation: str, risk: str, visibility: list[str], identity_state: str, room_id: str | None, endpoint_id: str | None) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        link = self._conn.execute("SELECT * FROM family_user_links WHERE user_id=? AND core_id=?", (user_id, self.core_id)).fetchone()
        reason, person = "person_not_linked", None
        if link is not None:
            person = self._conn.execute("SELECT * FROM family_people WHERE person_id=? AND core_id=? AND status='active'", (link["person_id"], self.core_id)).fetchone()
            reason = "wrong_household" if person is not None and person["household_id"] != household_id else "identity_required"
        allowed = person is not None and person["household_id"] == household_id and identity_state in {"authenticated", "verified", "confirmed"}
        if risk == "personal_sensitive" and identity_state not in {"authenticated", "verified"}:
            allowed, reason = False, "identity_uncertain"
        if allowed and room_id and endpoint_id:
            assignment = self._conn.execute("SELECT * FROM family_endpoint_assignments WHERE endpoint_id=? AND room_id=? AND household_id=? AND core_id=?", (endpoint_id, room_id, household_id, self.core_id)).fetchone()
            if assignment is None: allowed, reason = False, "wrong_room"
        consent_rows = []
        if allowed:
            consent_rows = self._conn.execute("SELECT * FROM family_consents WHERE person_id=? AND purpose=? AND core_id=? AND status='active'", (person["person_id"], operation, self.core_id)).fetchall()
            live = [row for row in consent_rows if not row["expires_at"] or datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00")) > now]
            if any(row["decision"] == "denied" for row in live): allowed, reason = False, "consent_denied"
            elif not any(row["decision"] == "granted" for row in live): allowed, reason = False, "consent_required"
        issued, expires = now.isoformat(), (now + timedelta(seconds=120)).isoformat()
        person_id = str(person["person_id"]) if person is not None else None
        return {
            "contract_version": "hexe.family-identity-authorization.v1", "authorization_id": f"authz_{secrets.token_urlsafe(16)}",
            "core_id": self.core_id, "household_id": household_id,
            "requester": {"user_id": user_id, **({"person_id": person_id} if person_id else {}), "session_id": session_id, **({"device_id": device_id} if device_id else {})},
            "participants": [{**({"person_id": person_id} if person_id else {}), "identity_state": identity_state}],
            "context": {"room_id": room_id, "endpoint_id": endpoint_id},
            "operation": {"kind": operation, "risk": risk, "requested_visibility": visibility},
            "decision": {"effect": "allow" if allowed else "deny", "allowed_person_ids": [person_id] if allowed else [], "allowed_visibility": visibility if allowed else [], "allowed_actions": [operation] if allowed else [], "consent_ids": [str(row["consent_id"]) for row in consent_rows if row["decision"] == "granted"] if allowed else [], "policy_version": "v1", **({"reason": reason} if not allowed else {})},
            "issued_at": issued, "expires_at": expires, "jti": f"jti_{secrets.token_urlsafe(18)}",
        }
