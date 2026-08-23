from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.system.auth import ServiceTokenKeyStore
from app.system.mqtt import router_legacy
from app.system.mqtt.integration_state import MqttIntegrationStateStore
from app.system.mqtt.router import build_mqtt_router


class _FakeSettingsStore:
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    async def get(self, key: str):  # noqa: ANN001
        return self._data.get(key)

    async def set(self, key: str, value):  # noqa: ANN001
        self._data[key] = value
        return value


def _route_signature(router) -> list[tuple[str, tuple[str, ...], bool, str]]:  # noqa: ANN001
    signatures: list[tuple[str, tuple[str, ...], bool, str]] = []
    for route in router.routes:
        path = str(getattr(route, "path", ""))
        methods = tuple(sorted(str(method) for method in getattr(route, "methods", []) or []))
        include_in_schema = bool(getattr(route, "include_in_schema", True))
        name = str(getattr(route, "name", ""))
        signatures.append((path, methods, include_in_schema, name))
    return sorted(signatures)


class TestMqttRouterComposition(unittest.TestCase):
    def test_domain_composed_router_preserves_legacy_route_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            args = {
                "manager": object(),
                "registry": object(),
                "state_store": MqttIntegrationStateStore(str(Path(tmpdir) / "mqtt_state.json")),
                "key_store": ServiceTokenKeyStore(_FakeSettingsStore()),
            }

            legacy_router = router_legacy.build_mqtt_router(**args)
            composed_router = build_mqtt_router(**args)

        self.assertEqual(_route_signature(composed_router), _route_signature(legacy_router))


if __name__ == "__main__":
    unittest.main()
