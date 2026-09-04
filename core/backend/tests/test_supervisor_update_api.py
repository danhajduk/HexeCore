from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.supervisor.models import SupervisorUpdateStartRequest
from app.supervisor.router import build_supervisor_router
from app.supervisor.service import SupervisorDomainService
from app.supervisor.update_package import build_supervisor_update_package


def _completed(args: list[str], stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr=stderr)


class TestSupervisorUpdateApi(unittest.TestCase):
    def _install_root(self, tmp: str, *, git: bool = True, updater: bool = True) -> Path:
        root = Path(tmp)
        if git:
            (root / ".git").mkdir()
        scripts = root / "scripts"
        scripts.mkdir()
        update_script = scripts / "update.sh"
        if updater:
            update_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            update_script.chmod(update_script.stat().st_mode | stat.S_IXUSR)
        return root

    def _git_result(self, args: list[str], *, timeout_s: float = 5.0) -> subprocess.CompletedProcess[str]:
        if args == ["rev-parse", "--is-inside-work-tree"]:
            return _completed(["git", *args], "true\n")
        if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return _completed(["git", *args], "main\n")
        if args == ["rev-parse", "HEAD"]:
            return _completed(["git", *args], "local-sha\n")
        if args == ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]:
            return _completed(["git", *args], "origin/main\n")
        if args == ["rev-parse", "origin/main"]:
            return _completed(["git", *args], "remote-sha\n")
        if args == ["rev-list", "--left-right", "--count", "HEAD...origin/main"]:
            return _completed(["git", *args], "0 1\n")
        if args == ["status", "--porcelain"]:
            return _completed(["git", *args], "")
        return _completed(["git", *args], stderr="unexpected git command", returncode=1)

    def _systemctl_show(self, active_state: str = "inactive", result: str = "success") -> str:
        return "\n".join(
            [
                "LoadState=loaded",
                f"ActiveState={active_state}",
                "SubState=dead",
                f"Result={result}",
                "ExecMainStatus=0",
                "InactiveEnterTimestamp=Wed 2026-09-02 08:00:00 PDT",
                "",
            ]
        )

    def test_status_reports_git_capability_and_update_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = SupervisorDomainService(install_root=self._install_root(tmp))
            with patch.dict(os.environ, {"HEXE_SUPERVISOR_ID": "sup-1", "HEXE_CORE_VERSION": "0.6.2"}), patch.object(
                service,
                "_run_git",
                side_effect=self._git_result,
            ), patch.object(
                service,
                "_run_systemctl_user",
                return_value=_completed(["systemctl"], self._systemctl_show()),
            ):
                status = service.supervisor_update_status()

        self.assertEqual(status.supervisor_id, "sup-1")
        self.assertEqual(status.reported_version, "0.6.2")
        self.assertTrue(status.source_is_git_checkout)
        self.assertEqual(status.supported_modes, ["git", "core_host"])
        self.assertEqual(status.git["behind"], 1)
        self.assertTrue(status.git["update_available"])
        self.assertTrue(status.package["supported"])

    def test_status_reports_package_config_version_before_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_root = self._install_root(tmp)
            (install_root / "config").mkdir()
            (install_root / "config" / "supervisor.json").write_text(
                '{ "schema_version": "hexe.supervisor.config.v1", "version": "0.6.3" }\n',
                encoding="utf-8",
            )
            service = SupervisorDomainService(install_root=install_root)
            with patch.dict(os.environ, {"HEXE_SUPERVISOR_ID": "sup-1", "HEXE_CORE_VERSION": "0.6.2"}), patch.object(
                service,
                "_run_git",
                side_effect=self._git_result,
            ), patch.object(
                service,
                "_run_systemctl_user",
                return_value=_completed(["systemctl"], self._systemctl_show()),
            ):
                status = service.supervisor_update_status()

        self.assertEqual(status.reported_version, "0.6.3")

    def test_status_fails_closed_for_non_git_tree_and_missing_unit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = SupervisorDomainService(install_root=self._install_root(tmp, git=False))
            with patch.object(
                service,
                "_run_systemctl_user",
                return_value=_completed(["systemctl"], self._systemctl_show().replace("LoadState=loaded", "LoadState=not-found")),
            ):
                status = service.supervisor_update_status()

        self.assertFalse(status.source_is_git_checkout)
        self.assertEqual(status.supported_modes, ["core_host"])
        self.assertEqual(status.unsupported_reasons["git"], "source_path_is_not_git_checkout")
        self.assertFalse(status.updater["unit_loaded"])

    def test_start_git_update_uses_bounded_updater_unit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = SupervisorDomainService(install_root=self._install_root(tmp))

            def systemctl(args: list[str], *, timeout_s: float = 8.0) -> subprocess.CompletedProcess[str]:
                if args[:2] == ["show", "hexe-updater.service"]:
                    return _completed(["systemctl", *args], self._systemctl_show(active_state="active"))
                if args == ["start", "hexe-updater.service"]:
                    return _completed(["systemctl", *args])
                return _completed(["systemctl", *args], stderr="unexpected systemctl command", returncode=1)

            with patch.object(service, "_run_git", side_effect=self._git_result), patch.object(
                service,
                "_run_systemctl_user",
                side_effect=systemctl,
            ) as systemctl_mock:
                result = service.start_supervisor_update(
                    SupervisorUpdateStartRequest(source_mode="git", idempotency_key="update-1234")
                )

        self.assertTrue(result.accepted)
        self.assertEqual(result.source_mode, "git")
        self.assertEqual(result.state, "running")
        self.assertIn("git", result.status.supported_modes)
        self.assertIn((["start", "hexe-updater.service"],), [call.args for call in systemctl_mock.call_args_list])

    def test_start_core_host_mode_requires_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = FastAPI()
            app.include_router(build_supervisor_router(SupervisorDomainService(install_root=self._install_root(tmp))), prefix="/api")
            client = TestClient(app)
            with patch.object(SupervisorDomainService, "_run_git", side_effect=self._git_result), patch.object(
                SupervisorDomainService,
                "_run_systemctl_user",
                return_value=_completed(["systemctl"], self._systemctl_show()),
            ):
                response = client.post(
                    "/api/supervisor/update/start",
                    json={"source_mode": "core_host", "idempotency_key": "update-1234"},
                )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["error"], "supervisor_update_package_required")

    def test_start_core_host_package_applies_files_with_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_root = self._install_root(tmp, git=False, updater=False)
            (install_root / "backend" / "app").mkdir(parents=True)
            (install_root / "backend" / "app" / "main.py").write_text("old\n", encoding="utf-8")
            source = Path(tmp) / "source"
            (source / "backend" / "app").mkdir(parents=True)
            (source / "backend" / "app" / "main.py").write_text("new\n", encoding="utf-8")
            (source / "scripts").mkdir()
            (source / "scripts" / "update.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            package = build_supervisor_update_package(source)
            service = SupervisorDomainService(install_root=install_root)

            result = service.start_supervisor_update(
                SupervisorUpdateStartRequest(
                    source_mode="core_host",
                    idempotency_key="package-1234",
                    **package.to_request_payload(),
                )
            )

            self.assertTrue(result.accepted)
            self.assertEqual(result.state, "succeeded")
            self.assertEqual((install_root / "backend" / "app" / "main.py").read_text(encoding="utf-8"), "new\n")
            last = service._read_update_state()["last_update"]
            self.assertEqual(last["package_id"], package.package_id)
            self.assertTrue(Path(last["backup_path"]).exists())

            replay = service.start_supervisor_update(
                SupervisorUpdateStartRequest(
                    source_mode="core_host",
                    idempotency_key="package-replay",
                    **package.to_request_payload(),
                )
            )
            self.assertFalse(replay.accepted)
            self.assertEqual(replay.message, "update_package_already_applied")

    def test_start_core_host_package_invalid_checksum_fails_before_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_root = self._install_root(tmp, git=False, updater=False)
            source = Path(tmp) / "source"
            (source / "backend").mkdir(parents=True)
            (source / "backend" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
            package = build_supervisor_update_package(source)
            payload = package.to_request_payload()
            payload["package_archive_sha256"] = "0" * 64
            service = SupervisorDomainService(install_root=install_root)

            with self.assertRaises(Exception) as raised:
                service.start_supervisor_update(
                    SupervisorUpdateStartRequest(
                        source_mode="core_host",
                        idempotency_key="bad-package-1234",
                        **payload,
                    )
                )

            self.assertEqual(getattr(raised.exception, "status_code", None), 422)
            last = service._read_update_state()["last_update"]
            self.assertEqual(last["state"], "failed")
            self.assertFalse(last["rollback_required"])

    def test_start_core_host_service_update_records_dependency_failure_and_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_root = self._install_root(tmp, git=False, updater=False)
            (install_root / "backend").mkdir(exist_ok=True)
            (install_root / "backend" / "requirements.txt").write_text("old\n", encoding="utf-8")
            source = Path(tmp) / "source"
            (source / "backend").mkdir(parents=True)
            (source / "backend" / "requirements.txt").write_text("new\n", encoding="utf-8")
            package = build_supervisor_update_package(source)
            service = SupervisorDomainService(install_root=install_root)

            with patch.object(
                service,
                "_run_package_dependency_install",
                return_value=_completed(["pip"], stderr="password=leaked", returncode=1),
            ):
                with self.assertRaises(Exception) as raised:
                    service.start_supervisor_update(
                        SupervisorUpdateStartRequest(
                            source_mode="core_host",
                            idempotency_key="dependency-fail-1234",
                            service_update=True,
                            **package.to_request_payload(),
                        )
                    )

            self.assertEqual(getattr(raised.exception, "status_code", None), 500)
            last = service._read_update_state()["last_update"]
            self.assertEqual(last["state"], "failed")
            self.assertTrue(last["rollback_required"])
            self.assertTrue(Path(last["backup_path"]).exists())
            self.assertNotIn("leaked", last["error"])

    def test_start_core_host_service_update_defers_api_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_root = self._install_root(tmp, git=False, updater=False)
            (install_root / "backend").mkdir(exist_ok=True)
            (install_root / "backend" / "requirements.txt").write_text("old\n", encoding="utf-8")
            source = Path(tmp) / "source"
            (source / "backend").mkdir(parents=True)
            (source / "backend" / "requirements.txt").write_text("new\n", encoding="utf-8")
            package = build_supervisor_update_package(source)
            service = SupervisorDomainService(install_root=install_root)
            systemctl_calls: list[list[str]] = []

            def systemctl(args: list[str], *, timeout_s: float = 8.0) -> subprocess.CompletedProcess[str]:  # noqa: ARG001
                systemctl_calls.append(args)
                if args == ["daemon-reload"] or args == ["try-restart", "hexe-supervisor.service"]:
                    return _completed(["systemctl", *args])
                return _completed(["systemctl", *args], stderr="unexpected systemctl command", returncode=1)

            with patch.object(service, "_run_package_dependency_install", return_value=_completed(["pip"])), patch.object(
                service,
                "_run_systemctl_user",
                side_effect=systemctl,
            ), patch.object(
                service,
                "_schedule_supervisor_api_restart",
                return_value={"unit": "hexe-supervisor-api.service", "exit_code": 0, "deferred": True, "scheduler": "test"},
            ) as schedule_api_restart:
                result = service.start_supervisor_update(
                    SupervisorUpdateStartRequest(
                        source_mode="core_host",
                        idempotency_key="service-update-1234",
                        service_update=True,
                        **package.to_request_payload(),
                    )
                )

            self.assertTrue(result.accepted)
            self.assertEqual(result.state, "succeeded")
            self.assertIn(["try-restart", "hexe-supervisor.service"], systemctl_calls)
            self.assertNotIn(["try-restart", "hexe-supervisor-api.service"], systemctl_calls)
            schedule_api_restart.assert_called_once_with()
            last = service._read_update_state()["last_update"]
            self.assertEqual(last["state"], "succeeded")
            self.assertEqual(last["service_update_results"]["restarts"][-1]["scheduler"], "test")

    def test_concurrent_update_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = SupervisorDomainService(install_root=self._install_root(tmp))
            service._write_update_state(
                {
                    "current_update": {
                        "state": "running",
                        "source_mode": "git",
                        "idempotency_key": "first-key",
                    }
                }
            )
            with patch.object(service, "_run_git", side_effect=self._git_result), patch.object(
                service,
                "_run_systemctl_user",
                return_value=_completed(["systemctl"], self._systemctl_show(active_state="active")),
            ):
                with self.assertRaises(Exception) as raised:
                    service.start_supervisor_update(
                        SupervisorUpdateStartRequest(source_mode="git", idempotency_key="second-key")
                    )
        self.assertEqual(getattr(raised.exception, "status_code", None), 409)
        self.assertEqual(raised.exception.detail["error"], "supervisor_update_already_running")

    def test_idempotent_retry_returns_existing_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = SupervisorDomainService(install_root=self._install_root(tmp))
            service._write_update_state(
                {
                    "current_update": {
                        "state": "running",
                        "source_mode": "git",
                        "idempotency_key": "same-key",
                    }
                }
            )
            with patch.object(service, "_run_git", side_effect=self._git_result), patch.object(
                service,
                "_run_systemctl_user",
                return_value=_completed(["systemctl"], self._systemctl_show(active_state="active")),
            ):
                result = service.start_supervisor_update(
                    SupervisorUpdateStartRequest(source_mode="git", idempotency_key="same-key")
                )

        self.assertTrue(result.accepted)
        self.assertEqual(result.message, "update_request_already_accepted")
        self.assertEqual(result.state, "running")

    def test_update_errors_are_redacted(self) -> None:
        service = SupervisorDomainService()
        redacted = service._redact_update_text("token=abc123\npassword=hunter2\nplain failure")
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("hunter2", redacted)
        self.assertIn("[REDACTED]", redacted)
        self.assertIn("plain failure", redacted)


if __name__ == "__main__":
    unittest.main()
