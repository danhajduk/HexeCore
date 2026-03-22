import unittest

from starlette.requests import Request

from app.reverse_proxy import ReverseProxyService


def _request(method: str = "GET", path: str = "/addons/mqtt/status", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": headers or [
            (b"host", b"core.local:9001"),
            (b"accept", b"text/html"),
            (b"cookie", b"session=secret"),
            (b"user-agent", b"pytest"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("core.local", 9001),
    }

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


class TestReverseProxyService(unittest.TestCase):
    def test_build_target_url_preserves_safe_special_path_chars(self) -> None:
        target = ReverseProxyService.build_target_url(
            "http://10.0.0.100:8081",
            "@vite/client",
            "t=123",
        )
        self.assertEqual(target, "http://10.0.0.100:8081/@vite/client?t=123")

    def test_build_request_headers_injects_forwarded_headers_without_cookie_leak(self) -> None:
        service = ReverseProxyService()
        request = _request()

        headers = service.build_request_headers(
            request,
            public_prefix="/addons/mqtt",
            extra_headers={"X-Hexe-Addon-Id": "mqtt"},
        )

        self.assertEqual(headers["accept"], "text/html")
        self.assertEqual(headers["user-agent"], "pytest")
        self.assertEqual(headers["X-Forwarded-Host"], "core.local:9001")
        self.assertEqual(headers["X-Forwarded-Proto"], "https")
        self.assertEqual(headers["X-Forwarded-Prefix"], "/addons/mqtt")
        self.assertEqual(headers["X-Hexe-Addon-Id"], "mqtt")
        self.assertNotIn("Cookie", headers)


if __name__ == "__main__":
    unittest.main()
