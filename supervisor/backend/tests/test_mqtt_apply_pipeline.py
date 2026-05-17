import asyncio
import tempfile
import unittest
from pathlib import Path

from app.system.mqtt.apply_pipeline import MqttApplyPipeline
from app.system.mqtt.authority_audit import MqttAuthorityAuditStore
from app.system.mqtt.runtime_boundary import InMemoryBrokerRuntimeBoundary


class TestMqttApplyPipeline(unittest.TestCase):
    def test_apply_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            live_dir = str(Path(tmp) / "live")
            staged_dir = str(Path(tmp) / "staged")
            audit = MqttAuthorityAuditStore(str(Path(tmp) / "audit.db"))
            boundary = InMemoryBrokerRuntimeBoundary()
            asyncio.run(boundary.ensure_running())
            pipeline = MqttApplyPipeline(
                runtime_boundary=boundary,
                audit_store=audit,
                live_dir=live_dir,
                staged_dir=staged_dir,
            )
            result = asyncio.run(pipeline.apply({"broker.conf": "listener 1883\n"}))
            self.assertTrue(result.ok)
            self.assertEqual(result.status, "applied")
            self.assertTrue((Path(live_dir) / "broker.conf").exists())
            self.assertTrue((Path(staged_dir) / "broker.conf").exists())
            self.assertEqual(
                (Path(staged_dir) / "broker.conf").read_text(encoding="utf-8"),
                (Path(live_dir) / "broker.conf").read_text(encoding="utf-8"),
            )

    def test_apply_validation_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            live_dir = str(Path(tmp) / "live")
            audit = MqttAuthorityAuditStore(str(Path(tmp) / "audit.db"))
            boundary = InMemoryBrokerRuntimeBoundary()
            pipeline = MqttApplyPipeline(runtime_boundary=boundary, audit_store=audit, live_dir=live_dir)
            result = asyncio.run(pipeline.apply({}))
            self.assertFalse(result.ok)
            self.assertEqual(result.status, "failed_validation")


if __name__ == "__main__":
    unittest.main()
