from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from app.system.settings.store import SettingsStore

KEYRING_SETTING_KEY = "auth.service_token.keys"
MAX_KEY_HISTORY = 3


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _json_bytes(data: dict[str, Any]) -> bytes:
    return json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _utc_ts() -> int:
    return int(time.time())


@dataclass
class ServiceTokenClaims:
    sub: str
    aud: str
    scp: list[str]
    exp: int
    jti: str
    iat: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "sub": self.sub,
            "aud": self.aud,
            "scp": self.scp,
            "exp": self.exp,
            "jti": self.jti,
            "iat": self.iat,
        }


class ServiceTokenError(ValueError):
    pass


class ServiceTokenKeyStore:
    def __init__(self, settings: SettingsStore) -> None:
        self._settings = settings

    async def ensure_keyring(self) -> list[dict[str, Any]]:
        ring = await self._settings.get(KEYRING_SETTING_KEY)
        if isinstance(ring, list) and any(isinstance(k, dict) for k in ring):
            return [k for k in ring if isinstance(k, dict)]
        now = _utc_ts()
        new_key = {
            "kid": f"k-{now}",
            "secret": secrets.token_urlsafe(48),
            "created_at": now,
            "active": True,
        }
        ring = [new_key]
        await self._settings.set(KEYRING_SETTING_KEY, ring)
        return ring

    async def rotate(self) -> list[dict[str, Any]]:
        ring = await self.ensure_keyring()
        for key in ring:
            key["active"] = False
        now = _utc_ts()
        ring.insert(
            0,
            {
                "kid": f"k-{now}",
                "secret": secrets.token_urlsafe(48),
                "created_at": now,
                "active": True,
            },
        )
        ring = ring[:MAX_KEY_HISTORY]
        await self._settings.set(KEYRING_SETTING_KEY, ring)
        return ring

    async def active_key(self) -> dict[str, Any]:
        ring = await self.ensure_keyring()
        for key in ring:
            if bool(key.get("active")):
                return key
        ring = await self.rotate()
        return ring[0]

    async def all_keys(self) -> list[dict[str, Any]]:
        return await self.ensure_keyring()


def sign_hs256(header: dict[str, Any], payload: dict[str, Any], secret: str) -> str:
    h = _b64url_encode(_json_bytes(header))
    p = _b64url_encode(_json_bytes(payload))
    signing_input = f"{h}.{p}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url_encode(sig)}"


def verify_hs256(token: str, candidate_keys: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ServiceTokenError("token_format_invalid")
    h64, p64, s64 = parts
    try:
        header = json.loads(_b64url_decode(h64))
        payload = json.loads(_b64url_decode(p64))
    except Exception as e:
        raise ServiceTokenError("token_decode_failed")
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise ServiceTokenError("token_decode_failed")
    if header.get("alg") != "HS256":
        raise ServiceTokenError("token_alg_unsupported")

    kid = str(header.get("kid") or "")
    signed = f"{h64}.{p64}".encode("ascii")
    expected_sig = _b64url_decode(s64)

    ordered_keys = candidate_keys
    if kid:
        ordered_keys = sorted(candidate_keys, key=lambda x: 0 if str(x.get("kid")) == kid else 1)

    for key in ordered_keys:
        secret = str(key.get("secret") or "")
        if not secret:
            continue
        sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).digest()
        if hmac.compare_digest(sig, expected_sig):
            return header, payload
    raise ServiceTokenError("token_signature_invalid")


def validate_claims(payload: dict[str, Any], audience: str, required_scopes: list[str] | None = None) -> ServiceTokenClaims:
    now = _utc_ts()
    sub = str(payload.get("sub") or "")
    aud = payload.get("aud")
    scp = payload.get("scp")
    exp = payload.get("exp")
    jti = str(payload.get("jti") or "")
    iat = int(payload.get("iat") or 0)

    if not sub:
        raise ServiceTokenError("claim_sub_missing")
    if isinstance(aud, list):
        aud_ok = audience in [str(x) for x in aud]
        aud_value = audience if aud_ok else ""
    else:
        aud_value = str(aud or "")
        aud_ok = aud_value == audience
    if not aud_ok:
        raise ServiceTokenError("claim_aud_invalid")
    if not isinstance(scp, list):
        raise ServiceTokenError("claim_scp_invalid")
    scopes = [str(x) for x in scp]
    if required_scopes:
        for needed in required_scopes:
            if needed not in scopes:
                raise ServiceTokenError("claim_scope_missing")
    if not isinstance(exp, int):
        raise ServiceTokenError("claim_exp_invalid")
    if exp <= now:
        raise ServiceTokenError("token_expired")
    if not jti:
        raise ServiceTokenError("claim_jti_missing")
    return ServiceTokenClaims(sub=sub, aud=aud_value, scp=scopes, exp=exp, jti=jti, iat=iat)
