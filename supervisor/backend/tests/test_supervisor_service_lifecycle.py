from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.supervisor import SupervisorDomainService
from app.system.runtime import StandaloneRuntimeService


class TestSupervisorServiceLifecycle(unittest.TestCase):
    def _runtime_service(self, services_root: Path) -> StandaloneRuntimeService:
        return StandaloneRuntimeService(
            cmd_runner=lambda _cmd: None,
            services_root_resolver=lambda create=False: services_root,
            service_addon_dir_resolver=lambda addon_id, create=False: services_root / addon_id,
        )

    def test_lifecycle_actions_write_runtime_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            services_root = Path(tmpdir) / "services"
            addon_dir = services_root / "mqtt"
            current_dir = addon_dir / "current"
            current_dir.mkdir(parents=True, exist_ok=True)
            compose_path = current_dir / "docker-compose.yml"
            compose_path.write_text("services: {}\n", encoding="utf-8")

            desired_path = addon_dir / "desired.json"
            desired_path.write_text(
                json.dumps(
                    {
                        "addon_id": "mqtt",
                        "desired_state": "running",
                        "runtime": {"project_name": "synthia-addon-mqtt", "ports": []},
                        "install_source": {"type": "catalog", "release": {"artifact_url": "https://example.test/mqtt.tgz"}},
                        "config": {"env": {}},
                        "ssap_version": "1.0",
                    }
                ),
                encoding="utf-8",
            )
            runtime_path = addon_dir / "runtime.json"
            runtime_path.write_text(
                json.dumps(
                    {
                        "state": "running",
                        "active_version": "1.0.0",
                        "compose_files_in_use": [str(compose_path)],
                    }
                ),
                encoding="utf-8",
            )

            service = SupervisorDomainService(self._runtime_service(services_root))

            with patch("app.supervisor.service.compose_up") as compose_up_mock, patch(
                "app.supervisor.service.compose_down"
            ) as compose_down_mock:
                service.stop_managed_node("mqtt")
                stopped = json.loads(runtime_path.read_text(encoding="utf-8"))
                self.assertEqual(stopped["lifecycle_state"], "stopped")
                self.assertEqual(stopped["last_action"], "stop")
                compose_down_mock.assert_called_once()

                service.start_managed_node("mqtt")
                started = json.loads(runtime_path.read_text(encoding="utf-8"))
                self.assertEqual(started["lifecycle_state"], "running")
                self.assertEqual(started["last_action"], "start")
                compose_up_mock.assert_called_once()

                service.restart_managed_node("mqtt")
                restarted = json.loads(runtime_path.read_text(encoding="utf-8"))
                self.assertEqual(restarted["lifecycle_state"], "running")
                self.assertEqual(restarted["last_action"], "restart")

    def test_apply_cloudflared_config_starts_docker_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "SYNTHIA_EDGE_RUNTIME_DIR": tmpdir,
                    "SYNTHIA_CLOUDFLARED_PROVIDER": "docker",
                },
                clear=False,
            ):
                service = SupervisorDomainService(self._runtime_service(Path(tmpdir) / "services"))
                completed = [
                    subprocess.CompletedProcess(["docker"], 0, stdout="", stderr=""),
                    subprocess.CompletedProcess(["docker"], 0, stdout="container-123\n", stderr=""),
                    subprocess.CompletedProcess(["docker"], 0, stdout="true\n", stderr=""),
                ]
                with patch("app.supervisor.service.shutil.which", return_value="/usr/bin/docker"), patch(
                    "app.supervisor.service.subprocess.run", side_effect=completed
                ) as run_mock:
                    result = service.apply_cloudflared_config(
                        {
                            "tunnel": "tunnel-123",
                            "tunnel-token": "token-123",
                            "desired_enabled": True,
                        }
                    )
                    runtime = service.get_runtime_state("cloudflared")
                self.assertTrue(result["ok"])
                self.assertEqual(result["runtime_state"], "running")
                self.assertTrue(runtime["exists"])
                self.assertEqual(runtime["provider"], "docker")
                self.assertEqual(runtime["state"], "running")
                docker_run = next(
                    " ".join(call.args[0])
                    for call in run_mock.call_args_list
                    if len(call.args) == 1 and isinstance(call.args[0], list) and "run" in call.args[0]
                )
                self.assertIn("--network host", docker_run)
                self.assertIn("cloudflare/cloudflared:latest", docker_run)

    def test_apply_cloudflared_config_disabled_provider_keeps_runtime_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "SYNTHIA_EDGE_RUNTIME_DIR": tmpdir,
                    "SYNTHIA_CLOUDFLARED_PROVIDER": "disabled",
                },
                clear=False,
            ):
                service = SupervisorDomainService(self._runtime_service(Path(tmpdir) / "services"))
                result = service.apply_cloudflared_config(
                    {
                        "tunnel": "tunnel-123",
                        "tunnel-token": "token-123",
                        "desired_enabled": True,
                    }
                )
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"], "cloudflared_runtime_disabled")


if __name__ == "__main__":
    unittest.main()
