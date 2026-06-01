from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import psutil

from app.supervisor import (
    SupervisorCoreRuntimeRegistrationRequest,
    SupervisorDomainService,
    SupervisorRuntimeRegistrationRequest,
)
from app.supervisor.core_runtime_store import SupervisorCoreRuntimeStore
from app.supervisor.resource_monitor import SupervisorResourceMonitor
from app.supervisor.runtime_store import SupervisorRuntimeNodesStore


class _MemoryInfo:
    rss = 123456


class _FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    def cpu_percent(self, interval=None) -> float:  # noqa: ANN001
        return 7.5

    def memory_percent(self) -> float:
        return 1.25

    def memory_info(self) -> _MemoryInfo:
        return _MemoryInfo()

    def status(self) -> str:
        return "running"


class _FakeHistoryStore:
    def __init__(self) -> None:
        self.samples: list[dict[str, object]] = []
        self.events: list[dict[str, object]] = []

    def insert_sample(self, **kwargs):  # noqa: ANN001
        self.samples.append(kwargs)

    def record_event(self, **kwargs):  # noqa: ANN001
        self.events.append(kwargs)


class TestSupervisorRuntimeResourceHistory(unittest.TestCase):
    def _service(self, root: Path, history: _FakeHistoryStore) -> SupervisorDomainService:
        monitor = SupervisorResourceMonitor(
            process_factory=lambda pid: _FakeProcess(pid),
            docker_available=lambda: False,
            systemctl_available=lambda: False,
            gpu_available=lambda: False,
        )
        return SupervisorDomainService(
            runtime_nodes_store=SupervisorRuntimeNodesStore(path=root / "runtime_nodes.json"),
            core_runtime_store=SupervisorCoreRuntimeStore(path=root / "core_runtimes.json"),
            resource_monitor=monitor,
            resource_history_store=history,
        )

    def test_registered_runtime_summary_records_aggregate_and_nested_service_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history = _FakeHistoryStore()
            service = self._service(Path(tmpdir), history)

            service.register_runtime(
                SupervisorRuntimeRegistrationRequest(
                    node_id="node-1",
                    node_name="AI Node",
                    node_type="ai",
                    runtime_metadata={"services": [{"service_id": "worker", "pid": 1234}]},
                )
            )

        runtime_sample = next(item for item in history.samples if item["scope"] == "runtime")
        self.assertEqual(runtime_sample["resource_id"], "node-1")
        self.assertEqual(runtime_sample["metrics"]["cpu_percent"], 7.5)
        self.assertEqual(runtime_sample["metrics"]["mem_percent"], 1.25)
        self.assertEqual(runtime_sample["metadata"]["node_type"], "ai")

        service_sample = next(item for item in history.samples if item["scope"] == "runtime_service")
        self.assertEqual(service_sample["resource_id"], "node-1/worker")
        self.assertEqual(service_sample["metrics"]["pid"], 1234)
        self.assertEqual(service_sample["metrics"]["resource_source"], "supervisor_pid")
        self.assertEqual(service_sample["metadata"]["parent_resource_id"], "node-1")

    def test_core_runtime_summary_records_process_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history = _FakeHistoryStore()
            service = self._service(Path(tmpdir), history)

            service.register_core_runtime(
                SupervisorCoreRuntimeRegistrationRequest(
                    runtime_id="core-api",
                    runtime_name="Hexe Core API",
                    runtime_metadata={"pid": 4321},
                )
            )

        sample = next(item for item in history.samples if item["scope"] == "core_runtime")
        self.assertEqual(sample["resource_id"], "core-api")
        self.assertEqual(sample["metrics"]["pid"], 4321)
        self.assertEqual(sample["metrics"]["cpu_percent"], 7.5)
        self.assertEqual(sample["metadata"]["runtime_kind"], "core_service")

    def test_registered_runtime_action_records_lifecycle_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history = _FakeHistoryStore()
            service = self._service(Path(tmpdir), history)
            service.register_runtime(
                SupervisorRuntimeRegistrationRequest(
                    node_id="node-1",
                    node_name="AI Node",
                    node_type="ai",
                )
            )
            history.events.clear()

            service.start_registered_runtime("node-1")

        marker = next(item for item in history.events if item["event_type"] == "start_requested")
        self.assertEqual(marker["scope"], "runtime")
        self.assertEqual(marker["resource_id"], "node-1")
        self.assertEqual(marker["payload"]["action"], "start")

    def test_process_unavailable_sample_records_timeline_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history = _FakeHistoryStore()
            monitor = SupervisorResourceMonitor(
                process_factory=lambda pid: (_ for _ in ()).throw(psutil.NoSuchProcess(pid=pid)),
                docker_available=lambda: False,
                systemctl_available=lambda: False,
                gpu_available=lambda: False,
            )
            service = SupervisorDomainService(
                runtime_nodes_store=SupervisorRuntimeNodesStore(path=Path(tmpdir) / "runtime_nodes.json"),
                core_runtime_store=SupervisorCoreRuntimeStore(path=Path(tmpdir) / "core_runtimes.json"),
                resource_monitor=monitor,
                resource_history_store=history,
            )

            service.register_runtime(
                SupervisorRuntimeRegistrationRequest(
                    node_id="node-1",
                    node_name="AI Node",
                    node_type="ai",
                    runtime_metadata={"pid": 9876},
                )
            )

        marker = next(item for item in history.events if item["event_type"] == "process_unavailable")
        self.assertEqual(marker["scope"], "runtime")
        self.assertEqual(marker["resource_id"], "node-1")
        self.assertEqual(marker["payload"]["metrics"]["last_error"], "process_unavailable")


if __name__ == "__main__":
    unittest.main()
