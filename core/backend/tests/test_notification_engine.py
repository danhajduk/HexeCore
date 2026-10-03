from fastapi import FastAPI

from app.engines import IdentityAccessEngine, NotificationPolicyEngine, PeopleHouseholdEngine
from app.system.audit import AuditLogStore
from app.system.auth import ServiceTokenKeyStore
from app.system.settings.store import SettingsStore


class MqttStub:
    def register_message_listener(self, **kwargs): return "listener"
    def unregister_message_listener(self, listener_id): return None


def test_notification_engine_separates_policy_and_transport(tmp_path) -> None:
    database = str(tmp_path / "users.db")
    settings = SettingsStore(str(tmp_path / "settings.db"))
    keys = ServiceTokenKeyStore(settings)
    audit = AuditLogStore(str(tmp_path / "audit.log"))
    identity = IdentityAccessEngine.create(database_path=database, keys=keys, settings=settings, audit=audit)
    people = PeopleHouseholdEngine.create(database_path=database, core_id="core-test", identity=identity, keys=keys, audit=audit)
    notifications = NotificationPolicyEngine.create(database_path=database, core_id="core-test", identity=identity, people=people, settings=settings, audit=audit, mqtt_manager=MqttStub())
    app = FastAPI()
    notifications.mount_transport_routes(app, settings, audit)
    paths = {route.path for route in app.routes}
    assert "/api/web-app/notification-gateway/status" in paths
    assert "/api/web-app/notification-subscriptions/config" in paths
    assert "/api/web-app/notification-gateway/bootstrap" in paths
    assert notifications.transport.publisher is not notifications.policy
    assert notifications.identity is identity
    assert notifications.people is people
