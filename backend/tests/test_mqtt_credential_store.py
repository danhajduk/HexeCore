import tempfile
import unittest
from pathlib import Path

from app.system.mqtt.credential_store import MqttCredentialStore
from app.system.mqtt.integration_models import MqttIntegrationState, MqttPrincipal


class TestMqttCredentialStore(unittest.TestCase):
    def test_renders_credentials_for_active_principals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MqttCredentialStore(str(Path(tmp) / "credentials.json"))
            state = MqttIntegrationState(
                principals={
                    "addon:vision": MqttPrincipal(
                        principal_id="addon:vision",
                        principal_type="synthia_addon",
                        status="active",
                        logical_identity="vision",
                        username="vision",
                    ),
                    "user:guest1": MqttPrincipal(
                        principal_id="user:guest1",
                        principal_type="generic_user",
                        status="pending",
                        logical_identity="guest1",
                    ),
                    "addon:old": MqttPrincipal(
                        principal_id="addon:old",
                        principal_type="synthia_addon",
                        status="revoked",
                        logical_identity="old",
                    ),
                }
            )
            password_file = store.render_password_file(state)
            self.assertIn("vision:$7$", password_file)
            self.assertIn("gu_guest1:$7$", password_file)
            self.assertNotIn("old", password_file)


if __name__ == "__main__":
    unittest.main()
