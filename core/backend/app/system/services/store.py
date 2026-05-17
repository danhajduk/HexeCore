from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ServiceCatalogStore:
    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._lock = asyncio.Lock()

    async def all_catalogs(self) -> dict[str, dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._read_sync)

    async def upsert_catalog(self, service_name: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._upsert_sync, service_name, payload)

    async def upsert_service(
        self,
        *,
        service_type: str,
        addon_id: str,
        endpoint: str,
        health: str,
        capabilities: list[str],
        addon_registry: dict[str, Any],
        service_id: str | None = None,
        provider: str | None = None,
        models: list[Any] | None = None,
        declared_capacity: dict[str, Any] | None = None,
        auth_modes: list[str] | None = None,
        required_scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        service_key = str(service_id or f"{addon_id}:{service_type}").strip()
        auth_mode_list = [str(v).strip() for v in list(auth_modes or []) if str(v).strip()]
        payload = {
            "service_type": service_type,
            "addon_id": addon_id,
            "service_id": service_key,
            "service": service_type,
            "endpoint": endpoint,
            "base_url": endpoint,
            "health": health,
            "health_status": health,
            "capabilities": capabilities,
            "provider": str(provider or "").strip().lower() or None,
            "models": [item for item in list(models or [])],
            "declared_capacity": dict(declared_capacity or {}),
            "auth_mode": auth_mode_list[0] if auth_mode_list else "service_token",
            "auth_modes": auth_mode_list or ["service_token"],
            "required_scopes": [str(v).strip() for v in list(required_scopes or []) if str(v).strip()],
            "addon_registry": addon_registry,
        }
        await self.upsert_catalog(service_key, payload)
        catalogs = await self.all_catalogs()
        return catalogs.get(service_key, payload)

    async def resolve(self, capability: str) -> dict[str, Any] | None:
        capability = capability.strip()
        if not capability:
            return None
        catalogs = await self.all_catalogs()
        for service_name in sorted(catalogs.keys()):
            item = catalogs[service_name]
            caps = item.get("capabilities", [])
            if not isinstance(caps, list):
                continue
            if capability in [str(x) for x in caps]:
                return item
        return None

    def _read_sync(self) -> dict[str, dict[str, Any]]:
        if not os.path.exists(self.path):
            return {}
        try:
            raw = json.loads(open(self.path, "r", encoding="utf-8").read())
            if isinstance(raw, dict):
                out: dict[str, dict[str, Any]] = {}
                for k, v in raw.items():
                    if isinstance(v, dict):
                        out[str(k)] = v
                return out
        except Exception:
            return {}
        return {}

    def _write_sync(self, value: dict[str, dict[str, Any]]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, sort_keys=True)

    def _upsert_sync(self, service_name: str, payload: dict[str, Any]) -> None:
        data = self._read_sync()
        item = data.get(service_name, {})
        item.update(payload)
        item["service"] = service_name
        item["last_seen"] = _utcnow_iso()
        data[service_name] = item
        self._write_sync(data)
