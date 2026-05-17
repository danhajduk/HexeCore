import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

from app.supervisor.server import _post_supervisor_payload


class TestSupervisorCoreReporting(unittest.TestCase):
    def test_supervisor_token_kind_uses_supervisor_header(self) -> None:
        captured_headers: dict[str, str] = {}

        async def run() -> bool:
            def handler(request: httpx.Request) -> httpx.Response:
                captured_headers.update(dict(request.headers))
                return httpx.Response(200, json={"ok": True})

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                kwargs = {
                    "core_url": "http://core",
                    "token": "hexe_sup_report_test",
                    "path": "/api/system/supervisors/heartbeat",
                    "payload": {"supervisor_id": "host-a"},
                }
                return await _post_supervisor_payload(client, **kwargs)

        with patch.dict(os.environ, {"HEXE_SUPERVISOR_CORE_TOKEN_KIND": "supervisor"}, clear=False):
            self.assertTrue(asyncio.run(run()))

        self.assertEqual(captured_headers.get("x-supervisor-token"), "hexe_sup_report_test")
        self.assertNotIn("x-admin-token", captured_headers)

    def test_admin_token_kind_uses_admin_header(self) -> None:
        captured_headers: dict[str, str] = {}

        async def run() -> bool:
            def handler(request: httpx.Request) -> httpx.Response:
                captured_headers.update(dict(request.headers))
                return httpx.Response(200, json={"ok": True})

            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                kwargs = {
                    "core_url": "http://core",
                    "token": "admin-token",
                    "path": "/api/system/supervisors/heartbeat",
                    "payload": {"supervisor_id": "host-a"},
                }
                return await _post_supervisor_payload(client, **kwargs)

        with patch.dict(os.environ, {"HEXE_SUPERVISOR_CORE_TOKEN_KIND": "admin"}, clear=False):
            self.assertTrue(asyncio.run(run()))

        self.assertEqual(captured_headers.get("x-admin-token"), "admin-token")
        self.assertNotIn("x-supervisor-token", captured_headers)


if __name__ == "__main__":
    unittest.main()
