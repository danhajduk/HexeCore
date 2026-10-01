from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone


VALID_ROLES = {"owner", "admin", "member", "guest"}
DEFAULT_ITERATIONS = 200_000


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_password(password: str, *, salt: str | None = None, iterations: int = DEFAULT_ITERATIONS) -> str:
    selected_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        selected_salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${selected_salt}${digest}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iters_raw, salt, expected = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iters_raw)
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(actual, expected)


class UsersStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              username TEXT PRIMARY KEY,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL,
              enabled INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS consumed_refresh_tokens (
              refresh_verifier TEXT PRIMARY KEY,
              session_id TEXT NOT NULL,
              consumed_at TEXT NOT NULL
            )
            """
        )
        columns = {str(row["name"]) for row in cur.execute("PRAGMA table_info(users)").fetchall()}
        for name, definition in (
            ("user_id", "TEXT"),
            ("core_id", "TEXT"),
            ("username_key", "TEXT"),
            ("credential_revision", "INTEGER NOT NULL DEFAULT 1"),
            ("disabled_at", "TEXT"),
        ):
            if name not in columns:
                cur.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
        rows = cur.execute("SELECT username FROM users WHERE user_id IS NULL OR user_id = ''").fetchall()
        for row in rows:
            cur.execute("UPDATE users SET user_id = ? WHERE username = ?", (f"usr_{uuid.uuid4().hex}", row["username"]))
        for row in cur.execute("SELECT username FROM users WHERE username_key IS NULL OR username_key = ''").fetchall():
            cur.execute("UPDATE users SET username_key = ? WHERE username = ?", (str(row["username"]).strip().casefold(), row["username"]))
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_user_id_idx ON users(user_id)")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_username_key_idx ON users(username_key)")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS human_sessions (
              session_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              device_id TEXT,
              refresh_verifier TEXT NOT NULL UNIQUE,
              previous_refresh_verifier TEXT,
              credential_revision INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              last_used_at TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              revoked_at TEXT,
              revoke_reason TEXT
            )
            """
        )
        self._conn.commit()

    async def list_users(self) -> list[dict[str, object]]:
        return await self._run(self._list_users_sync)

    async def upsert_user(
        self,
        *,
        username: str,
        role: str,
        enabled: bool,
        password: str | None,
    ) -> dict[str, object]:
        return await self._run(self._upsert_user_sync, username, role, enabled, password)

    async def delete_user(self, username: str) -> bool:
        return await self._run(self._delete_user_sync, username)

    async def verify_credentials(self, username: str, password: str) -> dict[str, object] | None:
        return await self._run(self._verify_credentials_sync, username, password)

    async def get_user(self, username: str) -> dict[str, object] | None:
        return await self._run(self._get_user_sync, username)

    async def ensure_admin_user(self, username: str, password: str) -> None:
        await self._run(self._ensure_admin_user_sync, username, password)

    async def migrate_initial_owner(self, username: str, core_id: str) -> dict[str, object] | None:
        return await self._run(self._migrate_initial_owner_sync, username, core_id)

    async def create_session(self, *, user_id: str, device_id: str | None, refresh_verifier: str, expires_at: str) -> dict[str, object]:
        return await self._run(self._create_session_sync, user_id, device_id, refresh_verifier, expires_at)

    async def get_session(self, session_id: str) -> dict[str, object] | None:
        return await self._run(self._get_session_sync, session_id)

    async def list_sessions(self, user_id: str) -> list[dict[str, object]]:
        return await self._run(self._list_sessions_sync, user_id)

    async def rotate_session_refresh(self, *, refresh_verifier: str, replacement_verifier: str, expires_at: str) -> tuple[str, dict[str, object] | None]:
        return await self._run(self._rotate_session_refresh_sync, refresh_verifier, replacement_verifier, expires_at)

    async def revoke_session(self, session_id: str, *, reason: str, user_id: str | None = None) -> bool:
        return await self._run(self._revoke_session_sync, session_id, reason, user_id)

    async def revoke_user_sessions(self, user_id: str, *, reason: str) -> int:
        return await self._run(self._revoke_user_sessions_sync, user_id, reason)

    async def get_user_by_id(self, user_id: str) -> dict[str, object] | None:
        return await self._run(self._get_user_by_id_sync, user_id)

    async def _run(self, fn, *args):
        async with self._lock:
            return await asyncio.to_thread(fn, *args)

    def _validate_role(self, role: str) -> str:
        normalized = role.strip().lower()
        if normalized not in VALID_ROLES:
            raise RuntimeError("invalid_role")
        return normalized

    def _enabled_admin_count_sync(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS count FROM users WHERE role = 'admin' AND enabled = 1"
        ).fetchone()
        return int(row["count"] if row else 0)

    def _user_row_sync(self, username: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT username, password_hash, role, enabled, created_at, updated_at, user_id, core_id, credential_revision, disabled_at, username_key FROM users WHERE username_key = ?",
            (username.strip().casefold(),),
        ).fetchone()

    def _to_public_user(self, row: sqlite3.Row) -> dict[str, object]:
        return {
            "username": str(row["username"]),
            "role": str(row["role"]),
            "enabled": bool(int(row["enabled"])),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "user_id": str(row["user_id"] or ""),
            "core_id": str(row["core_id"] or ""),
            "credential_revision": int(row["credential_revision"] or 1),
            "disabled_at": str(row["disabled_at"]) if row["disabled_at"] else None,
        }

    def _list_users_sync(self) -> list[dict[str, object]]:
        rows = self._conn.execute(
            "SELECT username, role, enabled, created_at, updated_at, user_id, core_id, credential_revision, disabled_at FROM users ORDER BY username"
        ).fetchall()
        return [
            {
                "username": str(row["username"]),
                "role": str(row["role"]),
                "enabled": bool(int(row["enabled"])),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
                "user_id": str(row["user_id"] or ""),
                "core_id": str(row["core_id"] or ""),
                "credential_revision": int(row["credential_revision"] or 1),
                "disabled_at": str(row["disabled_at"]) if row["disabled_at"] else None,
            }
            for row in rows
        ]

    def _upsert_user_sync(self, username: str, role: str, enabled: bool, password: str | None) -> dict[str, object]:
        clean_username = username.strip()
        if not clean_username:
            raise RuntimeError("username_required")
        selected_role = self._validate_role(role)

        existing = self._user_row_sync(clean_username)
        if existing is None and (password is None or not password.strip()):
            raise RuntimeError("password_required_for_new_user")

        credential_changed = bool(password is not None and password.strip())
        if existing is not None:
            existing_role = str(existing["role"])
            existing_enabled = bool(int(existing["enabled"]))
            if existing_enabled:
                if existing_role == "owner" and (selected_role != "owner" or not enabled) and self._enabled_owner_count_sync() <= 1:
                    raise RuntimeError("last_enabled_owner_required")
                if self._enabled_owner_count_sync() == 0 and existing_role == "admin" and (selected_role != "admin" or not enabled) and self._enabled_admin_count_sync() <= 1:
                    raise RuntimeError("last_enabled_admin_required")
            credential_changed = credential_changed or existing_role != selected_role or existing_enabled != enabled

        now = _utcnow_iso()
        password_hash: str
        if password is not None and password.strip():
            password_hash = _hash_password(password)
        elif existing is not None:
            password_hash = str(existing["password_hash"])
        else:
            raise RuntimeError("password_required_for_new_user")

        created_at = str(existing["created_at"]) if existing is not None else now
        persisted_username = str(existing["username"]) if existing is not None else clean_username
        self._conn.execute(
            """
            INSERT INTO users (username, password_hash, role, enabled, created_at, updated_at, user_id, core_id, username_key, credential_revision, disabled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
              password_hash=excluded.password_hash,
              role=excluded.role,
              enabled=excluded.enabled,
              updated_at=excluded.updated_at,
              credential_revision=excluded.credential_revision,
              disabled_at=excluded.disabled_at
            """,
            (
                persisted_username,
                password_hash,
                selected_role,
                1 if enabled else 0,
                created_at,
                now,
                str(existing["user_id"]) if existing is not None else f"usr_{uuid.uuid4().hex}",
                str(existing["core_id"] or os.getenv("HEXE_CORE_ID", "hexe-core")) if existing is not None else str(os.getenv("HEXE_CORE_ID", "hexe-core")),
                persisted_username.casefold(),
                (int(existing["credential_revision"] or 1) + (1 if credential_changed else 0)) if existing is not None else 1,
                None if enabled else now,
            ),
        )
        self._conn.commit()
        row = self._user_row_sync(clean_username)
        if row is None:
            raise RuntimeError("user_save_failed")
        return self._to_public_user(row)

    def _delete_user_sync(self, username: str) -> bool:
        clean_username = username.strip()
        if not clean_username:
            return False
        row = self._user_row_sync(clean_username)
        if row is None:
            return False

        if bool(int(row["enabled"])):
            if str(row["role"]) == "owner" and self._enabled_owner_count_sync() <= 1:
                raise RuntimeError("last_enabled_owner_required")
            if self._enabled_owner_count_sync() == 0 and str(row["role"]) == "admin" and self._enabled_admin_count_sync() <= 1:
                raise RuntimeError("last_enabled_admin_required")

        self._conn.execute("DELETE FROM users WHERE username_key = ?", (clean_username.casefold(),))
        self._conn.commit()
        return True

    def _enabled_owner_count_sync(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'owner' AND enabled = 1").fetchone()
        return int(row["count"] if row else 0)

    def _verify_credentials_sync(self, username: str, password: str) -> dict[str, object] | None:
        row = self._user_row_sync(username.strip())
        if row is None:
            return None
        if not bool(int(row["enabled"])):
            return None
        if not _verify_password(password, str(row["password_hash"])):
            return None
        return self._to_public_user(row)

    def _get_user_sync(self, username: str) -> dict[str, object] | None:
        row = self._user_row_sync(username.strip())
        return self._to_public_user(row) if row is not None else None

    def _ensure_admin_user_sync(self, username: str, password: str) -> None:
        clean_username = username.strip()
        if not clean_username or not password:
            return
        row = self._user_row_sync(clean_username)
        if row is None:
            now = _utcnow_iso()
            self._conn.execute(
                "INSERT INTO users (username, password_hash, role, enabled, created_at, updated_at, user_id, core_id, username_key, credential_revision) VALUES (?, ?, 'admin', 1, ?, ?, ?, ?, ?, 1)",
                (clean_username, _hash_password(password), now, now, f"usr_{uuid.uuid4().hex}", str(os.getenv("HEXE_CORE_ID", "hexe-core")), clean_username.casefold()),
            )
            self._conn.commit()
            return

        self._conn.execute(
            "UPDATE users SET role = CASE WHEN role = 'owner' THEN role ELSE 'admin' END, enabled = 1, updated_at = ? WHERE username_key = ?",
            (_utcnow_iso(), clean_username.casefold()),
        )
        self._conn.commit()

    def _migrate_initial_owner_sync(self, username: str, core_id: str) -> dict[str, object] | None:
        row = self._user_row_sync(username.strip())
        if row is None:
            return None
        if not bool(int(row["enabled"])) or str(row["role"]) not in {"admin", "owner"}:
            raise RuntimeError("initial_owner_not_enabled_admin")
        now = _utcnow_iso()
        self._conn.execute(
            "UPDATE users SET role = 'owner', core_id = ?, credential_revision = credential_revision + CASE WHEN role = 'owner' THEN 0 ELSE 1 END, updated_at = ? WHERE username = ?",
            (core_id, now, str(row["username"])),
        )
        self._conn.execute("UPDATE users SET core_id = ? WHERE core_id IS NULL OR core_id = ''", (core_id,))
        self._conn.commit()
        return self._to_public_user(self._user_row_sync(username.strip()))

    def _session_row_sync(self, session_id: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM human_sessions WHERE session_id = ?", (session_id,)).fetchone()

    @staticmethod
    def _public_session(row: sqlite3.Row) -> dict[str, object]:
        return {key: row[key] for key in ("session_id", "user_id", "device_id", "created_at", "last_used_at", "expires_at", "revoked_at", "revoke_reason")}

    def _create_session_sync(self, user_id: str, device_id: str | None, refresh_verifier: str, expires_at: str) -> dict[str, object]:
        user = self._conn.execute("SELECT credential_revision FROM users WHERE user_id = ? AND enabled = 1", (user_id,)).fetchone()
        if user is None:
            raise RuntimeError("user_not_available")
        session_id = f"ses_{uuid.uuid4().hex}"
        now = _utcnow_iso()
        self._conn.execute("INSERT INTO human_sessions VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL, NULL)", (session_id, user_id, device_id, refresh_verifier, int(user["credential_revision"]), now, now, expires_at))
        self._conn.commit()
        return self._public_session(self._session_row_sync(session_id))

    def _get_session_sync(self, session_id: str) -> dict[str, object] | None:
        row = self._session_row_sync(session_id)
        return self._public_session(row) | {"credential_revision": int(row["credential_revision"])} if row else None

    def _list_sessions_sync(self, user_id: str) -> list[dict[str, object]]:
        return [self._public_session(row) for row in self._conn.execute("SELECT * FROM human_sessions WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()]

    def _rotate_session_refresh_sync(self, verifier: str, replacement: str, expires_at: str) -> tuple[str, dict[str, object] | None]:
        consumed = self._conn.execute("SELECT session_id FROM consumed_refresh_tokens WHERE refresh_verifier = ?", (verifier,)).fetchone()
        if consumed is not None:
            self._revoke_session_sync(str(consumed["session_id"]), "refresh_reuse", None)
            return "reused", None
        row = self._conn.execute("SELECT * FROM human_sessions WHERE refresh_verifier = ?", (verifier,)).fetchone()
        if row is None:
            return "invalid", None
        session_id = str(row["session_id"])
        if row["revoked_at"]:
            return "revoked", None
        try:
            if datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00")) <= datetime.now(timezone.utc):
                self._revoke_session_sync(session_id, "refresh_expired", None)
                return "revoked", None
        except ValueError:
            self._revoke_session_sync(session_id, "refresh_expiry_invalid", None)
            return "revoked", None
        user = self._conn.execute("SELECT * FROM users WHERE user_id = ?", (row["user_id"],)).fetchone()
        if user is None or not bool(int(user["enabled"])) or int(user["credential_revision"]) != int(row["credential_revision"]):
            self._revoke_session_sync(session_id, "user_credentials_changed", None)
            return "revoked", None
        now = _utcnow_iso()
        self._conn.execute("INSERT INTO consumed_refresh_tokens (refresh_verifier, session_id, consumed_at) VALUES (?, ?, ?)", (verifier, session_id, now))
        self._conn.execute("UPDATE human_sessions SET previous_refresh_verifier = refresh_verifier, refresh_verifier = ?, last_used_at = ?, expires_at = ? WHERE session_id = ?", (replacement, now, expires_at, session_id))
        self._conn.commit()
        return "ok", self._get_session_sync(session_id)

    def _revoke_session_sync(self, session_id: str, reason: str, user_id: str | None) -> bool:
        where = "session_id = ?" + (" AND user_id = ?" if user_id else "")
        params = (session_id, user_id) if user_id else (session_id,)
        cur = self._conn.execute(f"UPDATE human_sessions SET revoked_at = COALESCE(revoked_at, ?), revoke_reason = COALESCE(revoke_reason, ?) WHERE {where}", (_utcnow_iso(), reason, *params))
        self._conn.commit()
        return cur.rowcount > 0

    def _revoke_user_sessions_sync(self, user_id: str, reason: str) -> int:
        cur = self._conn.execute("UPDATE human_sessions SET revoked_at = COALESCE(revoked_at, ?), revoke_reason = COALESCE(revoke_reason, ?) WHERE user_id = ?", (_utcnow_iso(), reason, user_id))
        self._conn.commit()
        return int(cur.rowcount)

    def _get_user_by_id_sync(self, user_id: str) -> dict[str, object] | None:
        row = self._conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return self._to_public_user(row) if row else None
