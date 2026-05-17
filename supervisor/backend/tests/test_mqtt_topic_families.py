import unittest

from app.system.mqtt.topic_families import (
    BOOTSTRAP_TOPIC,
    is_addon_scoped_topic,
    is_bootstrap_topic,
    is_generic_non_reserved_topic,
    is_node_scoped_topic,
    is_policy_topic_path,
    is_platform_reserved_topic,
    is_reserved_family_topic,
    topic_family,
)


class TestMqttTopicFamilies(unittest.TestCase):
    def test_reserved_family_recognition(self) -> None:
        self.assertTrue(is_reserved_family_topic("hexe/core/mqtt/info"))
        self.assertTrue(is_reserved_family_topic("hexe/runtime/health"))
        self.assertTrue(is_reserved_family_topic("hexe/remote/node-1/state"))
        self.assertTrue(is_reserved_family_topic("hexe/bridges/edge-1/status"))
        self.assertTrue(is_reserved_family_topic("hexe/import/frigate/event"))
        self.assertTrue(is_reserved_family_topic("hexe/policy/grants/vision"))
        self.assertFalse(is_reserved_family_topic("devices/home/state"))

    def test_addon_scoping(self) -> None:
        self.assertTrue(is_addon_scoped_topic("hexe/addons/vision/announce", addon_id="vision"))
        self.assertFalse(is_addon_scoped_topic("hexe/addons/other/announce", addon_id="vision"))
        self.assertEqual(topic_family("hexe/addons/vision/announce"), "addons")

    def test_node_scoping(self) -> None:
        self.assertTrue(is_node_scoped_topic("hexe/nodes/node-1/status/main", node_id="node-1"))
        self.assertFalse(is_node_scoped_topic("hexe/nodes/node-2/status/main", node_id="node-1"))
        self.assertEqual(topic_family("hexe/nodes/node-1/status/main"), "nodes")

    def test_bootstrap_only_topic(self) -> None:
        self.assertTrue(is_bootstrap_topic(BOOTSTRAP_TOPIC))
        self.assertFalse(is_bootstrap_topic("hexe/bootstrap/other"))

    def test_generic_user_reserved_vs_non_reserved(self) -> None:
        self.assertTrue(is_platform_reserved_topic("hexe/system/health"))
        self.assertTrue(is_platform_reserved_topic("hexe/runtime/health"))
        self.assertTrue(is_platform_reserved_topic("hexe/remote/cluster/info"))
        self.assertFalse(is_generic_non_reserved_topic("hexe/system/health"))
        self.assertTrue(is_generic_non_reserved_topic("devices/home/state"))
        self.assertFalse(is_generic_non_reserved_topic("hexe/addons/vision/announce"))

    def test_policy_topic_path_validation(self) -> None:
        self.assertTrue(is_policy_topic_path("hexe/policy/grants/vision"))
        self.assertTrue(is_policy_topic_path("hexe/policy/revocations/grant-1"))
        self.assertFalse(is_policy_topic_path("hexe/policy/grants"))
        self.assertFalse(is_policy_topic_path("hexe/policy/other/vision"))


if __name__ == "__main__":
    unittest.main()
