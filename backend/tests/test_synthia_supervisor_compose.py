from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from synthia_supervisor.docker_compose import ensure_compose_files
from synthia_supervisor.models import DesiredState


class TestSynthiaSupervisorCompose(unittest.TestCase):
    def test_compose_defaults_include_security_guardrails(self) -> None:
        desired = DesiredState.model_validate(
            {
                "ssap_version": "1.0",
                "addon_id": "mqtt",
                "desired_state": "running",
                "install_source": {
                    "type": "catalog",
                    "release": {
                        "artifact_url": "https://example.test/mqtt.tgz",
                        "sha256": "a" * 64,
                        "publisher_key_id": "publisher.dan#2026-02",
                        "signature": {"type": "ed25519", "value": "sig"},
                    },
                },
                "runtime": {
                    "project_name": "synthia-addon-mqtt",
                    "network": "synthia_net",
                    "ports": [{"host": 9002, "container": 9002, "proto": "tcp"}],
                },
                "config": {"env": {"CORE_URL": "http://127.0.0.1:9001"}},
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            extracted = Path(tmp) / "extracted"
            extracted.mkdir(parents=True, exist_ok=True)
            compose_file = Path(tmp) / "docker-compose.yml"
            env_file = Path(tmp) / "runtime.env"
            with patch.dict(os.environ, {"SYNTHIA_SERVICE_TOKEN": "token-123"}, clear=False):
                ensure_compose_files(desired, extracted, compose_file, env_file)

            compose_text = compose_file.read_text(encoding="utf-8")
            env_text = env_file.read_text(encoding="utf-8")
            self.assertIn("privileged: false", compose_text)
            self.assertIn("no-new-privileges:true", compose_text)
            self.assertNotIn("network_mode: host", compose_text)
            self.assertIn("networks:", compose_text)
            self.assertIn("synthia_net", compose_text)
            self.assertIn("127.0.0.1:9002:9002/tcp", compose_text)
            self.assertIn("CORE_URL=http://127.0.0.1:9001", env_text)
            self.assertIn("SYNTHIA_SERVICE_TOKEN=token-123", env_text)


if __name__ == "__main__":
    unittest.main()
