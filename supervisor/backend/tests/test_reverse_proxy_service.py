import unittest

from starlette.requests import Request

from app.reverse_proxy import ReverseProxyService


def _request(method: str = "GET", path: str = "/addons/proxy/mqtt/status", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
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
            public_prefix="/addons/proxy/mqtt",
            extra_headers={"X-Hexe-Addon-Id": "mqtt"},
        )

        self.assertEqual(headers["accept"], "text/html")
        self.assertEqual(headers["user-agent"], "pytest")
        self.assertEqual(headers["X-Forwarded-Host"], "core.local:9001")
        self.assertEqual(headers["X-Forwarded-Proto"], "https")
        self.assertEqual(headers["X-Forwarded-Prefix"], "/addons/proxy/mqtt")
        self.assertEqual(headers["X-Hexe-Addon-Id"], "mqtt")
        self.assertNotIn("Cookie", headers)

    def test_build_request_headers_preserves_outer_tunnel_forwarded_host_and_proto(self) -> None:
        service = ReverseProxyService()
        request = _request(
            path="/nodes/proxy/no-json/node-1/google/gmail/callback",
            headers=[
                (b"host", b"127.0.0.1:9001"),
                (b"x-forwarded-host", b"a75d480287c33cab.hexe-ai.com"),
                (b"x-forwarded-proto", b"https"),
                (b"accept", b"text/html"),
            ],
        )

        headers = service.build_request_headers(
            request,
            public_prefix="/nodes/proxy/no-json/node-1",
            extra_headers={"X-Hexe-Node-Id": "node-1"},
        )

        self.assertEqual(headers["X-Forwarded-Host"], "a75d480287c33cab.hexe-ai.com")
        self.assertEqual(headers["X-Forwarded-Proto"], "https")
        self.assertEqual(headers["X-Forwarded-Prefix"], "/nodes/proxy/no-json/node-1")

    def test_build_request_headers_ignores_invalid_outer_forwarded_proto(self) -> None:
        service = ReverseProxyService()
        request = _request(
            headers=[
                (b"host", b"core.local:9001"),
                (b"x-forwarded-proto", b"javascript"),
            ],
        )

        headers = service.build_request_headers(request, public_prefix="/addons/proxy/mqtt")

        self.assertEqual(headers["X-Forwarded-Proto"], "https")

    def test_rewrite_root_relative_urls_respects_proxy_prefix_and_ignore_list(self) -> None:
        original = b"""
        <script src="/assets/main.js"></script>
        <a href="/addons/proxy/mqtt/already-proxied"></a>
        """
        rewritten = ReverseProxyService.rewrite_root_relative_urls(
            original,
            "text/html",
            proxy_prefix="/addons/proxy/mqtt",
            ignore_prefixes=("/addons/proxy/",),
        ).decode("utf-8")

        self.assertIn('src="/addons/proxy/mqtt/assets/main.js"', rewritten)
        self.assertIn('href="/addons/proxy/mqtt/already-proxied"', rewritten)


if __name__ == "__main__":
    unittest.main()
