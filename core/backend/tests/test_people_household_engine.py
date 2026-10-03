from fastapi import FastAPI

from app.engines import IdentityAccessEngine, PeopleHouseholdEngine
from app.system.audit import AuditLogStore
from app.system.auth import ServiceTokenKeyStore
from app.system.settings.store import SettingsStore


def test_people_engine_uses_identity_boundary_and_preserves_routes(tmp_path) -> None:
    database = str(tmp_path / "users.db")
    settings = SettingsStore(str(tmp_path / "settings.db"))
    keys = ServiceTokenKeyStore(settings)
    audit = AuditLogStore(str(tmp_path / "audit.log"))
    identity = IdentityAccessEngine.create(database_path=database, keys=keys, settings=settings, audit=audit)
    people = PeopleHouseholdEngine.create(database_path=database, core_id="core-test", identity=identity, keys=keys, audit=audit)
    app = FastAPI()
    people.mount_routes(app)
    paths = {route.path for route in app.routes}
    assert "/api/admin/family" in paths
    assert "/api/web-app/admin/family/user-links" in paths
    assert people.identity is identity
