import asyncio
import os
import shutil
import tempfile

import pytest

from app.core.web_push_vapid import VapidKeyMaterial, WebPushVapidKeyStore, vapid_key_id
from app.system.settings.store import SettingsStore


CORE_ID = "0123456789abcdef"


def test_vapid_key_id_uses_full_sha256_contract_fingerprint():
    assert vapid_key_id(CORE_ID, b"\x04" + b"\x00" * 64) == (
        "0123456789abcdef:web-push-vapid:We8aWgDzWxpyLaVspwtSpyHzOZhjTU-kJZMB8XD3tr0"
    )
    assert len(WebPushVapidKeyStore.generate(CORE_ID).key_id.rsplit(":", 1)[1]) == 43


def test_generated_vapid_key_round_trips_through_sensitive_settings_backup():
    with tempfile.TemporaryDirectory() as temporary:
        source_path = os.path.join(temporary, "settings.db")
        source = SettingsStore(source_path)
        keys = WebPushVapidKeyStore(source)
        material = keys.generate(CORE_ID)
        asyncio.run(keys.install(material, core_id=CORE_ID))

        assert asyncio.run(source.get_all()) == {}
        assert asyncio.run(keys.active(core_id=CORE_ID)) == material
        source._conn.close()

        restored_path = os.path.join(temporary, "restored.db")
        shutil.copy2(source_path, restored_path)
        restored = WebPushVapidKeyStore(SettingsStore(restored_path))
        assert asyncio.run(restored.active(core_id=CORE_ID)) == material


def test_private_jwk_mismatch_and_wrong_core_fail_closed():
    material = WebPushVapidKeyStore.generate(CORE_ID)
    malformed = VapidKeyMaterial(
        key_id=material.key_id,
        public_key=material.public_key,
        private_jwk={**material.private_jwk, "x": material.private_jwk["y"]},
        created_at=material.created_at,
    )
    with pytest.raises(ValueError, match="vapid_key_pair_mismatch"):
        WebPushVapidKeyStore.validate(malformed, core_id=CORE_ID)
    with pytest.raises(ValueError, match="vapid_key_pair_mismatch"):
        WebPushVapidKeyStore.validate(material, core_id="fedcba9876543210")
