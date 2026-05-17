import unittest

import httpx

from app.edge.cloudflare_client import CloudflareApiClient, CloudflareApiError


class TestCloudflareApiClient(unittest.IsolatedAsyncioTestCase):
    async def test_find_tunnel_by_name_and_create_tunnel(self) -> None:
        requests: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append((request.method, str(request.url)))
            if request.method == "GET":
                return httpx.Response(200, json={"success": True, "result": [{"id": "tun-1", "name": "hexe-core-abcd"}]})
            return httpx.Response(200, json={"success": True, "result": {"id": "tun-2", "name": "hexe-core-new"}})

        client = CloudflareApiClient(
            api_token="token",
            account_id="acct",
            zone_id="zone",
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

        found = await client.find_tunnel_by_name("hexe-core-abcd")
        created = await client.create_tunnel("hexe-core-new")

        self.assertEqual(found.tunnel_id, "tun-1")
        self.assertEqual(created.tunnel_name, "hexe-core-new")
        self.assertEqual(requests[0][0], "GET")
        self.assertEqual(requests[1][0], "POST")
        await client._client.aclose()

    async def test_upsert_dns_record_updates_existing_record(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(f"{request.method} {request.url.path}")
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "result": [{"id": "dns-1", "name": "api.core.hexe-ai.com", "content": "old.cfargotunnel.com", "proxied": True}],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {"id": "dns-1", "name": "api.core.hexe-ai.com", "content": "new.cfargotunnel.com", "proxied": True},
                },
            )

        client = CloudflareApiClient(
            api_token="token",
            account_id="acct",
            zone_id="zone",
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

        result = await client.upsert_dns_record(
            hostname="api.core.hexe-ai.com",
            content="new.cfargotunnel.com",
            proxied=True,
        )

        self.assertEqual(result.record_id, "dns-1")
        self.assertEqual(result.content, "new.cfargotunnel.com")
        self.assertEqual(seen, ["GET /client/v4/zones/zone/dns_records", "PUT /client/v4/zones/zone/dns_records/dns-1"])
        await client._client.aclose()

    async def test_error_mapping_raises_cloudflare_api_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"success": False, "errors": [{"message": "forbidden"}], "result": None})

        client = CloudflareApiClient(
            api_token="token",
            account_id="acct",
            zone_id="zone",
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

        with self.assertRaises(CloudflareApiError) as exc:
            await client.find_dns_record("core.hexe-ai.com")
        self.assertEqual(exc.exception.operation, "find_dns_record")
        self.assertEqual(exc.exception.status_code, 403)
        await client._client.aclose()
