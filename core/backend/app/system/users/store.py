from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timezone


VALID_ROLES = {"admin", "guest"}
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

    async def ensure_admin_user(self, username: str, password: str) -> None:
        await self._run(self._ensure_admin_user_sync, username, password)

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
            "SELECT username, password_hash, role, enabled, created_at, updated_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    def _to_public_user(self, row: sqlite3.Row) -> dict[str, object]:
        return {
            "username": str(row["username"]),
            "role": str(row["role"]),
            "enabled": bool(int(row["enabled"])),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def _list_users_sync(self) -> list[dict[str, object]]:
        rows = self._conn.execute(
            "SELECT username, role, enabled, created_at, updated_at FROM users ORDER BY username"
        ).fetchall()
        return [
            {
                "username": str(row["username"]),
                "role": str(row["role"]),
                "enabled": bool(int(row["enabled"])),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
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

        if existing is not None:
            existing_role = str(existing["role"])
            existing_enabled = bool(int(existing["enabled"]))
            if existing_role == "admin" and existing_enabled and (
                selected_role != "admin" or not enabled
            ):
                if self._enabled_admin_count_sync() <= 1:
                    raise RuntimeError("last_enabled_admin_required")

        now = _utcnow_iso()
        password_hash: str
        if password is not None and password.strip():
            password_hash = _hash_password(password)
        elif existing is not None:
            password_hash = str(existing["password_hash"])
        else:
            raise RuntimeError("password_required_for_new_user")

        created_at = str(existing["created_at"]) if existing is not None else now
        self._conn.execute(
            """
            INSERT INTO users (username, password_hash, role, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
              password_hash=excluded.password_hash,
              role=excluded.role,
              enabled=excluded.enabled,
              updated_at=excluded.updated_at
            """,
            (
                clean_username,
                password_hash,
                selected_role,
                1 if enabled else 0,
                created_at,
                now,
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

        if str(row["role"]) == "admin" and bool(int(row["enabled"])):
            if self._enabled_admin_count_sync() <= 1:
                raise RuntimeError("last_enabled_admin_required")

        self._conn.execute("DELETE FROM users WHERE username = ?", (clean_username,))
        self._conn.commit()
        return True

    def _verify_credentials_sync(self, username: str, password: str) -> dict[str, object] | None:
        row = self._user_row_sync(username.strip())
        if row is None:
            return None
        if not bool(int(row["enabled"])):
            return None
        if not _verify_password(password, str(row["password_hash"])):
            return None
        return self._to_public_user(row)

    def _ensure_admin_user_sync(self, username: str, password: str) -> None:
        clean_username = username.strip()
        if not clean_username or not password:
            return
        row = self._user_row_sync(clean_username)
        if row is None:
            now = _utcnow_iso()
            self._conn.execute(
                "INSERT INTO users (username, password_hash, role, enabled, created_at, updated_at) VALUES (?, ?, 'admin', 1, ?, ?)",
                (clean_username, _hash_password(password), now, now),
            )
            self._conn.commit()
            return

        self._conn.execute(
            "UPDATE users SET role = 'admin', enabled = 1, updated_at = ? WHERE username = ?",
            (_utcnow_iso(), clean_username),
        )
        self._conn.commit()
