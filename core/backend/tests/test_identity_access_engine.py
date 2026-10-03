from fastapi import FastAPI

from app.engines import IdentityAccessEngine
from app.system.audit import AuditLogStore
from app.system.auth import ServiceTokenKeyStore
from app.system.settings.store import SettingsStore


def test_identity_access_engine_owns_stores_and_preserves_routes(tmp_path) -> None:
    settings = SettingsStore(str(tmp_path / "settings.db"))
    engine = IdentityAccessEngine.create(
        database_path=str(tmp_path / "users.db"),
        keys=ServiceTokenKeyStore(settings),
        settings=settings,
        audit=AuditLogStore(str(tmp_path / "audit.log")),
    )
    app = FastAPI()
    engine.mount_admin_routes(app)
    engine.mount_authentication_routes(app)

    paths = {route.path for route in app.routes}
    assert "/api/admin/users" in paths
    assert "/api/web-app/admin/users" in paths
    assert "/api/auth/user/login" in paths
    assert "/api/auth/user/device-login/challenge" in paths
    assert "/api/auth/device-enrollments" in paths
    assert engine.users is not None
    assert engine.devices is not None
