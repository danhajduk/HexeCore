import unittest

from app.system.mqtt.config_renderer import MqttBrokerConfigRenderer, MqttBrokerRenderInput, MqttListenerSpec


class TestMqttConfigRenderer(unittest.TestCase):
    def test_renders_deterministic_file_set(self) -> None:
        renderer = MqttBrokerConfigRenderer()
        output = renderer.render(
            MqttBrokerRenderInput(
                provider="mosquitto",
                acl_file="/tmp/acl.conf",
                password_file="/tmp/passwords.conf",
                data_dir="/tmp/data",
                log_dir="/tmp/logs",
                listeners=[
                    MqttListenerSpec(name="main", enabled=True, port=1883),
                    MqttListenerSpec(name="bootstrap", enabled=True, port=1884, allow_anonymous=True),
                ],
            )
        )
        self.assertEqual(sorted(output.files.keys()), ["acl.conf", "auth.conf", "broker.conf", "listeners.conf"])
        self.assertIn("acl_file /tmp/acl.conf", output.files["acl.conf"])
        self.assertIn("password_file /tmp/passwords.conf", output.files["auth.conf"])
        self.assertIn("listener 1883 0.0.0.0", output.files["listeners.conf"])
        self.assertIn("listener 1884 0.0.0.0", output.files["listeners.conf"])
        self.assertIn("allow_anonymous true", output.files["listeners.conf"])


if __name__ == "__main__":
    unittest.main()
