from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, derive_private_key, generate_private_key

from app.system.settings.store import SettingsStore


VAPID_KEY_REF = "web_push_vapid_key_v1"


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def vapid_key_id(core_id: str, public_raw: bytes) -> str:
    fingerprint = _b64url(hashlib.sha256(public_raw).digest())
    return f"{core_id}:web-push-vapid:{fingerprint}"


@dataclass(frozen=True)
class VapidKeyMaterial:
    key_id: str
    public_key: str
    private_jwk: dict[str, Any]
    created_at: str

    def sensitive_record(self, *, core_id: str) -> dict[str, Any]:
        return {
            "contract_version": "hexe.web-push-vapid-key.v1",
            "core_id": core_id,
            "key_id": self.key_id,
            "public_key": self.public_key,
            "private_jwk": self.private_jwk,
            "created_at": self.created_at,
        }


class WebPushVapidKeyStore:
    def __init__(self, settings: SettingsStore, *, key_ref: str = VAPID_KEY_REF) -> None:
        self._settings = settings
        self._key_ref = key_ref

    @staticmethod
    def generate(core_id: str) -> VapidKeyMaterial:
        key = generate_private_key(SECP256R1())
        numbers = key.private_numbers()
        x = numbers.public_numbers.x.to_bytes(32, "big")
        y = numbers.public_numbers.y.to_bytes(32, "big")
        d = numbers.private_value.to_bytes(32, "big")
        public_raw = b"\x04" + x + y
        key_id = vapid_key_id(core_id, public_raw)
        return VapidKeyMaterial(
            key_id=key_id,
            public_key=_b64url(public_raw),
            private_jwk={
                "kty": "EC",
                "crv": "P-256",
                "x": _b64url(x),
                "y": _b64url(y),
                "d": _b64url(d),
                "key_ops": ["sign"],
                "ext": False,
            },
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def validate(material: VapidKeyMaterial, *, core_id: str) -> None:
        jwk = material.private_jwk
        if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256" or jwk.get("key_ops") != ["sign"] or jwk.get("ext") is not False:
            raise ValueError("vapid_private_jwk_invalid")
        try:
            x, y, d = _decode(str(jwk["x"])), _decode(str(jwk["y"])), _decode(str(jwk["d"]))
            if len(x) != 32 or len(y) != 32 or len(d) != 32:
                raise ValueError
            private_key = derive_private_key(int.from_bytes(d, "big"), SECP256R1())
            public_numbers = private_key.public_key().public_numbers()
            if public_numbers.x.to_bytes(32, "big") != x or public_numbers.y.to_bytes(32, "big") != y:
                raise ValueError
            public_raw = b"\x04" + x + y
            if material.public_key != _b64url(public_raw):
                raise ValueError
            if material.key_id != vapid_key_id(core_id, public_raw):
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("vapid_key_pair_mismatch") from exc

    async def active(self, *, core_id: str) -> VapidKeyMaterial | None:
        value = await self._settings.get_sensitive(self._key_ref)
        if not isinstance(value, dict) or value.get("core_id") != core_id:
            return None
        try:
            material = VapidKeyMaterial(
                key_id=str(value["key_id"]),
                public_key=str(value["public_key"]),
                private_jwk=dict(value["private_jwk"]),
                created_at=str(value["created_at"]),
            )
            self.validate(material, core_id=core_id)
            return material
        except (KeyError, TypeError, ValueError):
            return None

    async def install(self, material: VapidKeyMaterial, *, core_id: str) -> None:
        self.validate(material, core_id=core_id)
        await self._settings.set_sensitive(self._key_ref, material.sensitive_record(core_id=core_id))
