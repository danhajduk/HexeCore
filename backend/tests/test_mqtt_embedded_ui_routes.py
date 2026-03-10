import unittest

from fastapi.testclient import TestClient

from app.main import create_app


class TestMqttEmbeddedUiRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_root_ui_page_contains_setup_shell(self) -> None:
        res = self.client.get("/api/addons/mqtt")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIn("Synthia MQTT Setup", res.text)
        self.assertIn("Save and Initialize", res.text)
        self.assertIn("Local broker", res.text)
        self.assertIn("External broker", res.text)
        self.assertIn("Check Health", res.text)
        self.assertIn("data-runtime-action='start'", res.text)

    def test_subroute_ui_page_serves_same_shell(self) -> None:
        res = self.client.get("/api/addons/mqtt/principals")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIn("Synthia MQTT Setup", res.text)
        self.assertIn("data-section=\"principals\"", res.text)


if __name__ == "__main__":
    unittest.main()
