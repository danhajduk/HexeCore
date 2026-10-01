from app.edge.cloudflare_renderer import CloudflareConfigRenderer
from app.edge.models import CloudflareSettings, CorePublicIdentity


def test_public_ui_fallback_uses_hostname_aware_core_boundary() -> None:
    hostname = "0123456789abcdef.hexe-ai.com"
    rendered = CloudflareConfigRenderer().render(
        identity=CorePublicIdentity(
            core_id="0123456789abcdef",
            core_name="Test Core",
            platform_domain="hexe-ai.com",
            public_hostname=hostname,
            public_ui_hostname=hostname,
            public_api_hostname=hostname,
        ),
        settings=CloudflareSettings(tunnel_id="test-tunnel"),
        publications=[],
    )

    public_fallback = [
        item
        for item in rendered["ingress"]
        if item.get("hostname") == hostname and "path" not in item
    ]
    assert public_fallback == [{"hostname": hostname, "service": "http://127.0.0.1:9001"}]
