import asyncio
import os
import stat
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.system.settings.router import build_settings_router
from app.system.settings.store import SettingsStore


def test_sensitive_values_are_not_available_through_ordinary_settings_api():
    with tempfile.TemporaryDirectory() as temporary:
        store = SettingsStore(os.path.join(temporary, "settings.db"))
        assert stat.S_IMODE(os.stat(store.db_path).st_mode) == 0o600
        asyncio.run(store.set("ordinary", {"value": "visible"}))
        asyncio.run(store.set_sensitive("gateway", {"secret": "must-not-escape"}))
        app = FastAPI()
        app.include_router(build_settings_router(store), prefix="/api/system")
        client = TestClient(app)

        all_settings = client.get("/api/system/settings")
        assert all_settings.status_code == 200
        assert all_settings.json()["settings"] == {"ordinary": {"value": "visible"}}
        assert "must-not-escape" not in all_settings.text
        assert client.get("/api/system/settings/gateway").status_code == 404
        assert asyncio.run(store.get_sensitive("gateway")) == {"secret": "must-not-escape"}
        asyncio.run(store.delete_sensitive("gateway"))
        assert asyncio.run(store.get_sensitive("gateway")) is None


def test_sensitive_batch_is_committed_together():
    with tempfile.TemporaryDirectory() as temporary:
        store = SettingsStore(os.path.join(temporary, "settings.db"))
        asyncio.run(store.set_sensitive_many({"registration": {"version": 2}, "vapid": {"version": 2}}))

        assert asyncio.run(store.get_sensitive("registration")) == {"version": 2}
        assert asyncio.run(store.get_sensitive("vapid")) == {"version": 2}
