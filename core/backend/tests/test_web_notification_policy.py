import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timezone

from app.core.web_notification_policy import NotificationIntentStore, TrustedNotificationEvent, WebNotificationPolicyService
from app.system.auth.device_enrollment import NotificationPreferencesRequest, WebAppEnrollmentStore
from app.system.users import UsersStore


class TestWebNotificationPolicy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmp.name, "users.db")
        self.users = UsersStore(db_path)
        self.devices = WebAppEnrollmentStore(db_path)
        self.intents = NotificationIntentStore(os.path.join(self.tmp.name, "intents.db"))
        self.core_id = "core-test"
        self.service = WebNotificationPolicyService(self.devices, self.intents, core_id=self.core_id)

    def tearDown(self):
        self.tmp.cleanup()

    def add_target(self, name, role, device_id, *, privacy="generic", email=False, quiet_start=None, quiet_end=None, severity="info"):
        user = asyncio.run(self.users.upsert_user(username=name, role=role, enabled=True, password=f"{name}-pass"))
        now = datetime.now(timezone.utc).isoformat()
        self.devices._conn.execute(
            "INSERT INTO web_app_devices VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (device_id, self.core_id, user["user_id"], device_id, "public-key", "test", now, now),
        )
        self.devices._conn.execute(
            "INSERT INTO web_app_notification_subscriptions VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'active')",
            (device_id, self.core_id, user["user_id"], f"sub_{device_id}", "gateway-test", now, now),
        )
        categories = {
            "security": True, "approval-required": True, "task-completion": True,
            "timers-reminders": True, "device-health": True, "email-alerts": email,
        }
        asyncio.run(self.devices.put_notification_preferences(
            device_id=device_id, core_id=self.core_id, user_id=user["user_id"],
            preferences=NotificationPreferencesRequest(
                categories=categories, privacy_level=privacy,
                quiet_hours_start=quiet_start, quiet_hours_end=quiet_end,
                severity_threshold=severity,
            ),
        ))
        return user

    def test_untrusted_and_unsupported_events_are_suppressed(self):
        self.add_target("owner", "owner", "owner-phone")
        event = TrustedNotificationEvent(event_id="evt-1", event_type="security.login_failed", source_kind="core", source_id="auth")
        result = asyncio.run(self.service.route(event, trusted_source=False))
        self.assertEqual(result["reason"], "untrusted_source")
        self.assertEqual(asyncio.run(self.intents.list_pending()), [])
        unsupported = TrustedNotificationEvent(event_id="evt-2", event_type="weather.updated", source_kind="node", source_id="weather")
        self.assertEqual(asyncio.run(self.service.route(unsupported, trusted_source=True))["reason"], "category_unsupported")

    def test_same_security_event_is_role_scoped_and_privacy_varies_by_device(self):
        alice = self.add_target("alice", "member", "alice-phone", privacy="summary")
        self.add_target("owner", "owner", "owner-phone", privacy="generic")
        self.add_target("bob", "member", "bob-phone", privacy="summary")
        event = TrustedNotificationEvent(
            event_id="evt-security", event_type="security.login_failed", source_kind="core", source_id="auth",
            subject_user_id=alice["user_id"], summary="A new login was rejected", navigation_path="/app/security/events/evt-security",
        )
        result = asyncio.run(self.service.route(event, trusted_source=True))
        self.assertEqual(result["created"], 2)
        intents = asyncio.run(self.intents.list_pending())
        by_device = {item["device_id"]: item for item in intents}
        self.assertEqual(set(by_device), {"alice-phone", "owner-phone"})
        self.assertEqual(by_device["alice-phone"]["body"], "A new login was rejected")
        self.assertEqual(by_device["owner-phone"]["body"], "Open Hexe to view details.")
        self.assertNotIn("public-key", str(intents))

    def test_sensitive_email_is_generic_and_requires_explicit_opt_in(self):
        alice = self.add_target("alice", "member", "alice-phone", privacy="sensitive", email=True)
        self.add_target("bob", "member", "bob-phone", privacy="sensitive", email=False)
        event = TrustedNotificationEvent(
            event_id="evt-email", event_type="email.received", source_kind="node", source_id="email-node",
            subject_user_id=alice["user_id"], summary="Verification code 123456 in raw email body", sensitive=True,
        )
        result = asyncio.run(self.service.route(event, trusted_source=True))
        self.assertEqual(result["created"], 1)
        intent = asyncio.run(self.intents.list_pending())[0]
        self.assertEqual(intent["device_id"], "alice-phone")
        self.assertEqual(intent["body"], "Open Hexe to view details.")
        self.assertNotIn("123456", str(intent))

    def test_quiet_hours_severity_and_event_device_deduplication(self):
        alice = self.add_target("alice", "member", "alice-phone", quiet_start="22:00", quiet_end="07:00", severity="warning")
        event = TrustedNotificationEvent(
            event_id="evt-task", event_type="task.completed", source_kind="core", source_id="tasks",
            subject_user_id=alice["user_id"], severity="info",
        )
        at = datetime(2026, 10, 1, 23, 0, tzinfo=timezone.utc)
        self.assertEqual(asyncio.run(self.service.route(event, trusted_source=True, at=at))["created"], 0)
        critical = event.model_copy(update={"event_id": "evt-critical", "severity": "critical"})
        self.assertEqual(asyncio.run(self.service.route(critical, trusted_source=True, at=at))["created"], 1)
        replay = asyncio.run(self.service.route(critical, trusted_source=True, at=at))
        self.assertEqual(replay["deduplicated"], 1)


if __name__ == "__main__":
    unittest.main()
