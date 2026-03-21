from __future__ import annotations

import base64
import os
import secrets
from dataclasses import dataclass
from typing import Any

import httpx


class CloudflareApiError(RuntimeError):
    def __init__(self, operation: str, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code


@dataclass(frozen=True)
class CloudflareTunnel:
    tunnel_id: str
    tunnel_name: str
    created_at: str | None = None


@dataclass(frozen=True)
class CloudflareDnsRecord:
    record_id: str
    name: str
    content: str
    proxied: bool
    type: str = "CNAME"


class CloudflareApiClient:
    def __init__(
        self,
        *,
        api_token: str,
        account_id: str,
        zone_id: str,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_token = str(api_token or "").strip()
        self._account_id = str(account_id or "").strip()
        self._zone_id = str(zone_id or "").strip()
        self._base_url = str(base_url or os.getenv("CLOUDFLARE_API_BASE", "https://api.cloudflare.com/client/v4")).rstrip("/")
        self._client = client

    async def find_tunnel_by_name(self, tunnel_name: str) -> CloudflareTunnel | None:
        payload = await self._request(
            "GET",
            f"/accounts/{self._account_id}/cfd_tunnel",
            operation="find_tunnel_by_name",
            params={"name": tunnel_name},
        )
        results = payload if isinstance(payload, list) else []
        if not results:
            return None
        item = results[0]
        return CloudflareTunnel(
            tunnel_id=str(item.get("id") or "").strip(),
            tunnel_name=str(item.get("name") or "").strip(),
            created_at=str(item.get("created_at") or "").strip() or None,
        )

    async def get_tunnel(self, tunnel_id: str) -> CloudflareTunnel | None:
        payload = await self._request(
            "GET",
            f"/accounts/{self._account_id}/cfd_tunnel/{tunnel_id}",
            operation="get_tunnel",
            allow_not_found=True,
        )
        if not isinstance(payload, dict):
            return None
        return CloudflareTunnel(
            tunnel_id=str(payload.get("id") or "").strip(),
            tunnel_name=str(payload.get("name") or "").strip(),
            created_at=str(payload.get("created_at") or "").strip() or None,
        )

    async def create_tunnel(self, tunnel_name: str) -> CloudflareTunnel:
        secret = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        payload = await self._request(
            "POST",
            f"/accounts/{self._account_id}/cfd_tunnel",
            operation="create_tunnel",
            json={"name": tunnel_name, "config_src": "local", "tunnel_secret": secret},
        )
        return CloudflareTunnel(
            tunnel_id=str(payload.get("id") or "").strip(),
            tunnel_name=str(payload.get("name") or "").strip(),
            created_at=str(payload.get("created_at") or "").strip() or None,
        )

    async def get_tunnel_token(self, tunnel_id: str) -> str | None:
        payload = await self._request(
            "GET",
            f"/accounts/{self._account_id}/cfd_tunnel/{tunnel_id}/token",
            operation="get_tunnel_token",
            allow_not_found=True,
        )
        if isinstance(payload, dict):
            return str(payload.get("token") or "").strip() or None
        if isinstance(payload, str):
            return payload.strip() or None
        return None

    async def find_dns_record(self, hostname: str) -> CloudflareDnsRecord | None:
        payload = await self._request(
            "GET",
            f"/zones/{self._zone_id}/dns_records",
            operation="find_dns_record",
            params={"type": "CNAME", "name": hostname},
        )
        results = payload if isinstance(payload, list) else []
        if not results:
            return None
        item = results[0]
        return CloudflareDnsRecord(
            record_id=str(item.get("id") or "").strip(),
            name=str(item.get("name") or "").strip(),
            content=str(item.get("content") or "").strip(),
            proxied=bool(item.get("proxied", True)),
            type=str(item.get("type") or "CNAME").strip() or "CNAME",
        )

    async def upsert_dns_record(self, *, hostname: str, content: str, proxied: bool = True) -> CloudflareDnsRecord:
        current = await self.find_dns_record(hostname)
        payload = {"type": "CNAME", "name": hostname, "content": content, "proxied": proxied}
        if current is None:
            result = await self._request(
                "POST",
                f"/zones/{self._zone_id}/dns_records",
                operation="create_dns_record",
                json=payload,
            )
        elif current.content != content or bool(current.proxied) != bool(proxied):
            result = await self._request(
                "PUT",
                f"/zones/{self._zone_id}/dns_records/{current.record_id}",
                operation="update_dns_record",
                json=payload,
            )
        else:
            return current
        return CloudflareDnsRecord(
            record_id=str(result.get("id") or "").strip(),
            name=str(result.get("name") or "").strip(),
            content=str(result.get("content") or "").strip(),
            proxied=bool(result.get("proxied", True)),
            type=str(result.get("type") or "CNAME").strip() or "CNAME",
        )

    async def delete_dns_record(self, record_id: str) -> None:
        await self._request(
            "DELETE",
            f"/zones/{self._zone_id}/dns_records/{record_id}",
            operation="delete_dns_record",
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        allow_not_found: bool = False,
    ) -> Any:
        headers = {"Authorization": f"Bearer {self._api_token}", "Content-Type": "application/json"}
        if self._client is not None:
            response = await self._client.request(method, f"{self._base_url}{path}", headers=headers, params=params, json=json)
        else:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.request(method, f"{self._base_url}{path}", headers=headers, params=params, json=json)
        if allow_not_found and response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise CloudflareApiError(operation, response.text[:300], status_code=response.status_code)
        payload = response.json()
        if not isinstance(payload, dict):
            raise CloudflareApiError(operation, "cloudflare_payload_invalid")
        if payload.get("success") is False:
            errors = payload.get("errors")
            message = str(errors[0].get("message") if isinstance(errors, list) and errors and isinstance(errors[0], dict) else errors or "cloudflare_error")
            raise CloudflareApiError(operation, message, status_code=response.status_code)
        return payload.get("result")
