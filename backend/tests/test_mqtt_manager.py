import asyncio
import json
import unittest

from app.system.mqtt.manager import MqttManager


class _FakeSettingsStore:
    async def get(self, key: str):
        return None


class _FakeRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def update_from_mqtt_announce(self, addon_id: str, payload: dict) -> None:
        self.calls.append(("announce", addon_id, payload))

    def update_from_mqtt_health(self, addon_id: str, payload: dict) -> None:
        self.calls.append(("health", addon_id, payload))


class _FakeServiceCatalogStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def upsert_catalog(self, service_name: str, payload: dict) -> None:
        self.calls.append((service_name, payload))


class _Msg:
    def __init__(self, topic: str, payload: dict) -> None:
        self.topic = topic
        self.payload = json.dumps(payload).encode("utf-8")


class TestMqttManager(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_listener_is_noop(self) -> None:
        manager = MqttManager(
            settings_store=_FakeSettingsStore(),
            registry=_FakeRegistry(),
            service_catalog_store=_FakeServiceCatalogStore(),
            enabled=False,
        )
        await manager.start()
        status = await manager.status()
        self.assertFalse(status["enabled"])
        self.assertFalse(status["connected"])
        self.assertEqual(status["last_error"], "mqtt_disabled")

    async def test_dispatches_addon_announce_and_health(self) -> None:
        registry = _FakeRegistry()
        manager = MqttManager(
            settings_store=_FakeSettingsStore(),
            registry=registry,
            service_catalog_store=_FakeServiceCatalogStore(),
            enabled=True,
        )
        manager._loop = asyncio.get_running_loop()

        manager._on_message(None, None, _Msg("synthia/addons/mqtt/announce", {"base_url": "http://127.0.0.1:9100"}))
        manager._on_message(None, None, _Msg("synthia/addons/mqtt/health", {"status": "ok"}))
        await asyncio.sleep(0.02)

        self.assertEqual(len(registry.calls), 2)
        self.assertEqual(registry.calls[0][0], "announce")
        self.assertEqual(registry.calls[0][1], "mqtt")
        self.assertEqual(registry.calls[1][0], "health")
        self.assertEqual(registry.calls[1][1], "mqtt")


if __name__ == "__main__":
    unittest.main()
