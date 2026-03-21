from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from .models import CloudflareSettings, EdgePublication, EdgeTunnelStatus, utcnow_iso


class EdgeGatewayStore:
    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._lock = asyncio.Lock()

    async def load(self) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._read_sync)

    async def save(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._write_sync, payload)

    async def get_cloudflare_settings(self) -> CloudflareSettings:
        raw = (await self.load()).get("cloudflare")
        if isinstance(raw, dict):
            return CloudflareSettings.model_validate(raw)
        return CloudflareSettings()

    async def set_cloudflare_settings(self, settings: CloudflareSettings) -> CloudflareSettings:
        payload = await self.load()
        payload["cloudflare"] = settings.model_dump(mode="json")
        payload["updated_at"] = utcnow_iso()
        await self.save(payload)
        return settings

    async def list_publications(self) -> list[EdgePublication]:
        raw = (await self.load()).get("publications")
        if not isinstance(raw, list):
            return []
        out: list[EdgePublication] = []
        for item in raw:
            if isinstance(item, dict):
                out.append(EdgePublication.model_validate(item))
        return out

    async def set_publications(self, publications: list[EdgePublication]) -> None:
        payload = await self.load()
        payload["publications"] = [item.model_dump(mode="json") for item in publications]
        payload["updated_at"] = utcnow_iso()
        await self.save(payload)

    async def get_tunnel_status(self) -> EdgeTunnelStatus:
        raw = (await self.load()).get("tunnel")
        if isinstance(raw, dict):
            return EdgeTunnelStatus.model_validate(raw)
        return EdgeTunnelStatus()

    async def set_tunnel_status(self, status: EdgeTunnelStatus) -> EdgeTunnelStatus:
        payload = await self.load()
        payload["tunnel"] = status.model_dump(mode="json")
        payload["updated_at"] = utcnow_iso()
        await self.save(payload)
        return status

    async def get_reconcile_state(self) -> dict[str, Any]:
        raw = (await self.load()).get("reconcile_state")
        return dict(raw) if isinstance(raw, dict) else {}

    async def set_reconcile_state(self, state: dict[str, Any]) -> dict[str, Any]:
        payload = await self.load()
        payload["reconcile_state"] = dict(state)
        payload["updated_at"] = utcnow_iso()
        await self.save(payload)
        return dict(state)

    def _read_sync(self) -> dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except Exception:
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write_sync(self, payload: dict[str, Any]) -> None:
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
