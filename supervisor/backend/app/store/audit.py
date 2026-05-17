from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StoreAuditLogStore:
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
            CREATE TABLE IF NOT EXISTS store_audit_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              timestamp TEXT NOT NULL,
              action TEXT NOT NULL,
              addon_id TEXT NOT NULL,
              version TEXT,
              status TEXT NOT NULL,
              message TEXT NOT NULL,
              actor TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_store_audit_ts ON store_audit_log(timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_store_audit_addon ON store_audit_log(addon_id)")
        self._conn.commit()

    async def record(
        self,
        *,
        action: str,
        addon_id: str,
        version: str | None,
        status: str,
        message: str,
        actor: str | None,
    ) -> None:
        async with self._lock:
            await asyncio.to_thread(self._record_sync, action, addon_id, version, status, message, actor)

    async def list_rows(
        self,
        *,
        addon_id: str | None,
        action: str | None,
        status: str | None,
        from_ts: str | None,
        to_ts: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(
                self._list_rows_sync,
                addon_id,
                action,
                status,
                from_ts,
                to_ts,
                int(page),
                int(page_size),
            )

    def _record_sync(
        self,
        action: str,
        addon_id: str,
        version: str | None,
        status: str,
        message: str,
        actor: str | None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO store_audit_log (timestamp, action, addon_id, version, status, message, actor)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (_utcnow_iso(), action, addon_id, version, status, message, actor),
        )
        self._conn.commit()

    def _list_rows_sync(
        self,
        addon_id: str | None,
        action: str | None,
        status: str | None,
        from_ts: str | None,
        to_ts: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if addon_id:
            clauses.append("addon_id = ?")
            params.append(addon_id)
        if action:
            clauses.append("action = ?")
            params.append(action)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if from_ts:
            clauses.append("timestamp >= ?")
            params.append(from_ts)
        if to_ts:
            clauses.append("timestamp <= ?")
            params.append(to_ts)

        where = ""
        if clauses:
            where = " WHERE " + " AND ".join(clauses)

        count_sql = f"SELECT COUNT(*) AS c FROM store_audit_log{where}"
        total = int(self._conn.execute(count_sql, params).fetchone()["c"])

        page = max(1, int(page))
        page_size = max(1, min(200, int(page_size)))
        offset = (page - 1) * page_size

        query_sql = (
            "SELECT id, timestamp, action, addon_id, version, status, message, actor "
            f"FROM store_audit_log{where} "
            "ORDER BY id DESC "
            "LIMIT ? OFFSET ?"
        )
        rows = self._conn.execute(query_sql, [*params, page_size, offset]).fetchall()
        items = [
            {
                "id": int(r["id"]),
                "timestamp": r["timestamp"],
                "action": r["action"],
                "addon_id": r["addon_id"],
                "version": r["version"],
                "status": r["status"],
                "message": r["message"],
                "actor": r["actor"],
            }
            for r in rows
        ]
        return {
            "ok": True,
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": (offset + page_size) < total,
            "filters": {
                "addon_id": addon_id,
                "action": action,
                "status": status,
                "from_ts": from_ts,
                "to_ts": to_ts,
            },
        }
