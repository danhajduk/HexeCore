import json
import tempfile
import unittest
from pathlib import Path

from app.system.onboarding.registrations import NodeRegistrationRecord, NodeRegistrationsStore
from app.system.onboarding.sessions import NodeOnboardingSession


class TestNodeRegistrationsStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "node_registrations.json"
        self.store = NodeRegistrationsStore(path=self.path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_upsert_and_reload_record(self) -> None:
        record = NodeRegistrationRecord(
            node_id="node-001",
            node_type="ai-node",
            node_name="office-node",
            node_software_version="1.2.3",
            requested_node_type="ai-node",
            capabilities_summary=["vision", "alerts"],
            trust_status="approved",
            source_onboarding_session_id="sess-001",
            approved_by_user_id="admin:alice",
            approved_at="2026-03-11T00:00:00+00:00",
            created_at="2026-03-11T00:00:00+00:00",
            updated_at="2026-03-11T00:00:00+00:00",
            declared_capabilities=["task.classification", "task.captioning"],
            enabled_providers=["openai", "local-cpu"],
            capability_declaration_version="1.0",
            capability_declaration_timestamp="2026-03-11T00:00:05+00:00",
            capability_profile_id="cap-node-001-v1",
        )
        self.store.upsert(record)

        reloaded = NodeRegistrationsStore(path=self.path)
        by_id = reloaded.get("node-001")
        self.assertIsNotNone(by_id)
        assert by_id is not None
        self.assertEqual(by_id.node_name, "office-node")
        self.assertEqual(by_id.node_type, "ai-node")
        self.assertEqual(by_id.node_software_version, "1.2.3")
        self.assertEqual(by_id.trust_status, "approved")
        self.assertEqual(by_id.declared_capabilities, ["task.classification", "task.captioning"])
        self.assertEqual(by_id.enabled_providers, ["openai", "local-cpu"])
        self.assertEqual(by_id.capability_declaration_version, "1.0")
        self.assertEqual(by_id.capability_profile_id, "cap-node-001-v1")
        by_session = reloaded.get_by_session("sess-001")
        self.assertIsNotNone(by_session)
        assert by_session is not None
        self.assertEqual(by_session.node_id, "node-001")

    def test_backward_compatible_load_without_capability_metadata(self) -> None:
        payload = {
            "schema_version": "1",
            "items": [
                {
                    "node_id": "node-legacy",
                    "node_type": "ai-node",
                    "node_name": "legacy",
                    "node_software_version": "0.9.0",
                    "trust_status": "trusted",
                    "created_at": "2026-03-11T00:00:00+00:00",
                    "updated_at": "2026-03-11T00:00:00+00:00",
                }
            ],
            "session_to_node": {},
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        reloaded = NodeRegistrationsStore(path=self.path)
        item = reloaded.get("node-legacy")
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.declared_capabilities, [])
        self.assertEqual(item.enabled_providers, [])
        self.assertIsNone(item.capability_declaration_version)
        self.assertIsNone(item.capability_declaration_timestamp)
        self.assertIsNone(item.capability_profile_id)

    def test_upsert_from_approved_session_binds_session_mapping(self) -> None:
        session = NodeOnboardingSession(
            session_id="sess-448",
            session_state="approved",
            node_nonce="nonce-1",
            requested_node_name="kitchen-node",
            requested_node_type="ai-node",
            requested_node_software_version="2.0.0",
            requested_hostname=None,
            requested_from_ip=None,
            request_metadata={},
            created_at="2026-03-11T00:00:00+00:00",
            expires_at="2026-03-11T00:15:00+00:00",
            approved_at="2026-03-11T00:01:00+00:00",
            rejected_at=None,
            approved_by_user_id="admin:bob",
            rejection_reason=None,
            linked_node_id="node-448",
            final_payload_consumed_at=None,
            state_history=[],
        )

        created = self.store.upsert_from_approved_session(session)
        self.assertEqual(created.node_id, "node-448")
        self.assertEqual(created.source_onboarding_session_id, "sess-448")
        self.assertEqual(created.trust_status, "approved")
        self.assertEqual(created.node_name, "kitchen-node")

        api_payload = created.to_api_dict()
        self.assertEqual(api_payload["requested_node_name"], "kitchen-node")
        self.assertEqual(api_payload["requested_node_type"], "ai-node")
        self.assertEqual(api_payload["requested_node_software_version"], "2.0.0")

    def test_mark_trusted_by_session(self) -> None:
        record = NodeRegistrationRecord(
            node_id="node-910",
            node_type="sensor-node",
            node_name="sensor-north",
            node_software_version="4.2.1",
            requested_node_type="sensor-node",
            capabilities_summary=[],
            trust_status="approved",
            source_onboarding_session_id="sess-910",
            approved_by_user_id="admin:carol",
            approved_at="2026-03-11T00:00:00+00:00",
            created_at="2026-03-11T00:00:00+00:00",
            updated_at="2026-03-11T00:00:00+00:00",
        )
        self.store.upsert(record)
        updated = self.store.mark_trusted_by_session("sess-910")
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated.trust_status, "trusted")

    def test_set_trust_status_rejects_invalid_values(self) -> None:
        record = NodeRegistrationRecord(
            node_id="node-911",
            node_type="ai-node",
            node_name="vision-911",
            node_software_version="1.0.0",
            requested_node_type="ai-node",
            capabilities_summary=[],
            trust_status="approved",
            source_onboarding_session_id="sess-911",
            approved_by_user_id="admin",
            approved_at="2026-03-11T00:00:00+00:00",
            created_at="2026-03-11T00:00:00+00:00",
            updated_at="2026-03-11T00:00:00+00:00",
        )
        self.store.upsert(record)
        with self.assertRaisesRegex(ValueError, "trust_status_invalid"):
            self.store.set_trust_status("node-911", trust_status="invalid-state")


if __name__ == "__main__":
    unittest.main()
