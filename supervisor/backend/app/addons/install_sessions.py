from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .discovery import repo_root
from .registry import AddonRegistry


VALID_STATES = {
    "pending_permissions",
    "pending_deployment",
    "discovered",
    "registered",
    "configured",
    "verified",
    "installed",
    "error",
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class InstallSession:
    session_id: str
    addon_id: str
    state: str
    user_inputs: dict[str, Any]
    last_error: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "addon_id": self.addon_id,
            "state": self.state,
            "user_inputs": self.user_inputs,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class InstallSessionsStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (repo_root() / "data" / "addon_install_sessions.json")
        self._sessions: dict[str, InstallSession] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return
            for item in raw:
                if not isinstance(item, dict):
                    continue
                state = str(item.get("state") or "")
                if state not in VALID_STATES:
                    continue
                sid = str(item.get("session_id") or "").strip()
                addon_id = str(item.get("addon_id") or "").strip()
                if not sid or not addon_id:
                    continue
                created_at = str(item.get("created_at") or _utcnow_iso())
                updated_at = str(item.get("updated_at") or created_at)
                user_inputs = item.get("user_inputs") if isinstance(item.get("user_inputs"), dict) else {}
                last_error = item.get("last_error")
                self._sessions[sid] = InstallSession(
                    session_id=sid,
                    addon_id=addon_id,
                    state=state,
                    user_inputs=user_inputs,
                    last_error=str(last_error) if last_error else None,
                    created_at=created_at,
                    updated_at=updated_at,
                )
        except Exception:
            return

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [x.to_dict() for x in sorted(self._sessions.values(), key=lambda s: s.created_at)]
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _get(self, session_id: str) -> InstallSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError("session_not_found")
        return session

    def start(self, addon_id: str) -> InstallSession:
        addon = addon_id.strip()
        if not addon:
            raise ValueError("addon_id_required")
        now = _utcnow_iso()
        sid = secrets.token_urlsafe(18)
        session = InstallSession(
            session_id=sid,
            addon_id=addon,
            state="pending_permissions",
            user_inputs={},
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        self._sessions[sid] = session
        self._save()
        return session

    def get(self, session_id: str) -> InstallSession:
        return self._get(session_id)

    def approve_permissions(self, session_id: str) -> InstallSession:
        session = self._get(session_id)
        if session.state != "pending_permissions":
            raise ValueError("invalid_state_transition")
        session.state = "pending_deployment"
        session.updated_at = _utcnow_iso()
        self._save()
        return session

    def select_deployment(self, session_id: str, mode: str) -> InstallSession:
        session = self._get(session_id)
        if session.state not in {"pending_deployment", "discovered"}:
            raise ValueError("invalid_state_transition")
        selected = mode.strip().lower()
        if selected not in {"external", "embedded"}:
            raise ValueError("invalid_deployment_mode")
        session.user_inputs["deployment_mode"] = selected
        if session.state == "pending_deployment":
            session.state = "pending_deployment"
        session.updated_at = _utcnow_iso()
        self._save()
        return session

    def mark_discovered(self, addon_id: str) -> int:
        addon = addon_id.strip()
        if not addon:
            return 0
        changed = 0
        now = _utcnow_iso()
        for session in self._sessions.values():
            if session.addon_id != addon:
                continue
            if session.state == "pending_deployment":
                session.state = "discovered"
                session.updated_at = now
                changed += 1
        if changed:
            self._save()
        return changed

    async def configure(self, session_id: str, registry: AddonRegistry, config: dict[str, Any]) -> tuple[InstallSession, dict[str, Any]]:
        session = self._get(session_id)
        if session.state not in {"discovered", "registered", "configured"}:
            raise ValueError("invalid_state_transition")
        if session.addon_id not in registry.registered:
            raise RuntimeError("addon_not_registered")
        session.state = "registered"
        session.updated_at = _utcnow_iso()
        result = await registry.configure_registered(session.addon_id, config)
        session.state = "configured"
        session.last_error = None
        session.user_inputs["config"] = config
        session.updated_at = _utcnow_iso()
        self._save()
        return session, result

    async def verify(self, session_id: str, registry: AddonRegistry) -> tuple[InstallSession, dict[str, Any]]:
        session = self._get(session_id)
        if session.state not in {"configured", "verified"}:
            raise ValueError("invalid_state_transition")
        result = await registry.verify_registered(session.addon_id)
        status = str(result.get("status") or result.get("health_status") or "unknown").lower()
        if status in {"ok", "healthy", "ready"}:
            session.state = "verified"
            session.last_error = None
        else:
            session.state = "error"
            session.last_error = f"verify_status_{status}"
        session.updated_at = _utcnow_iso()
        self._save()
        return session, result
