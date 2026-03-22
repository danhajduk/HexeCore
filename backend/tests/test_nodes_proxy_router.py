import unittest

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.nodes.proxy import build_node_ui_proxy_router


class _FakeNodeProxy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def forward(self, request: Request, node_id: str, path: str = "") -> JSONResponse:
        self.calls.append((request.method, node_id, path))
        return JSONResponse(
            {
                "method": request.method,
                "node_id": node_id,
                "path": path,
            }
        )


class TestNodeUiProxyRouter(unittest.TestCase):
    def setUp(self) -> None:
        self.proxy = _FakeNodeProxy()
        app = FastAPI()
        app.include_router(build_node_ui_proxy_router(self.proxy))
        self.client = TestClient(app)

    def test_node_ui_routes_forward(self) -> None:
        checks = [
            ("/ui/nodes/node-1", ""),
            ("/ui/nodes/node-1/assets/main.js", "assets/main.js"),
        ]

        for url, expected_path in checks:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, resp.text)
            payload = resp.json()
            self.assertEqual(payload["node_id"], "node-1")
            self.assertEqual(payload["path"], expected_path)

        self.assertEqual(
            self.proxy.calls,
            [
                ("GET", "node-1", ""),
                ("GET", "node-1", "assets/main.js"),
            ],
        )

    def test_node_ui_routes_remain_get_head_only(self) -> None:
        denied = self.client.post("/ui/nodes/node-1")
        self.assertEqual(denied.status_code, 405, denied.text)

        head = self.client.head("/ui/nodes/node-1/status")
        self.assertEqual(head.status_code, 200, head.text)

        self.assertEqual(self.proxy.calls, [("HEAD", "node-1", "status")])


if __name__ == "__main__":
    unittest.main()
