from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from typing import Any, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.system.settings.store import SettingsStore


ASSISTANT_ASSERTION_KEYRING_REF = "assistant.assertion.signing_keys.v1"
ASSISTANT_AUTHORIZATION_EPOCHS_REF = "assistant.authorization_epochs.v1"
ASSISTANT_CONSUMED_APPROVALS_REF = "assistant.consumed_approvals.v1"
ASSISTANT_INTENT_EXECUTIONS_REF = "assistant.intent_executions.v1"
ASSISTANT_ENROLLMENT_GRANTS_REF = "assistant.speaker_enrollment_grants.v1"
ASSISTANT_ASSERTION_TTL_SECONDS = 60
ASSISTANT_ASSERTION_CLOCK_SKEW_SECONDS = 30
ASSISTANT_ASSERTION_MAX_KEY_HISTORY = 3


class AssistantAssertionError(ValueError):
    pass


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class AssistantAssertionKeyStore:
    def __init__(self, settings: SettingsStore) -> None:
        self._settings = settings

    @staticmethod
    def _new_key(now: int) -> dict[str, Any]:
        key = Ed25519PrivateKey.generate()
        private_raw = key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        public_raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return {
            "kid": f"assistant-{now}-{secrets.token_hex(4)}",
            "private_key": _b64url_encode(private_raw),
            "public_key": _b64url_encode(public_raw),
            "created_at": now,
            "active": True,
        }

    async def ensure_keyring(self) -> list[dict[str, Any]]:
        raw = await self._settings.get_sensitive(ASSISTANT_ASSERTION_KEYRING_REF)
        ring = [dict(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
        if ring and any(bool(item.get("active")) for item in ring):
            return ring
        ring.insert(0, self._new_key(int(time.time())))
        await self._settings.set_sensitive(ASSISTANT_ASSERTION_KEYRING_REF, ring)
        return ring

    async def active_key(self) -> dict[str, Any]:
        for key in await self.ensure_keyring():
            if bool(key.get("active")):
                return key
        raise AssistantAssertionError("assistant_signing_key_unavailable")

    async def record_expiry(self, *, kid: str, exp: int) -> None:
        ring = await self.ensure_keyring()
        changed = False
        for key in ring:
            if str(key.get("kid") or "") == kid and int(exp) > int(key.get("max_assertion_exp") or 0):
                key["max_assertion_exp"] = int(exp)
                changed = True
        if changed:
            await self._settings.set_sensitive(ASSISTANT_ASSERTION_KEYRING_REF, ring)

    async def rotate(self, *, now: int | None = None) -> list[dict[str, Any]]:
        selected_now = int(time.time()) if now is None else int(now)
        ring = await self.ensure_keyring()
        for key in ring:
            if bool(key.get("active")):
                key["active"] = False
                key["retired_at"] = selected_now
                key["verify_until"] = max(
                    int(key.get("max_assertion_exp") or selected_now) + ASSISTANT_ASSERTION_CLOCK_SKEW_SECONDS,
                    selected_now + ASSISTANT_ASSERTION_CLOCK_SKEW_SECONDS,
                )
        retained = [
            key for key in ring
            if int(key.get("verify_until") or 0) >= selected_now
        ][: ASSISTANT_ASSERTION_MAX_KEY_HISTORY - 1]
        next_ring = [self._new_key(selected_now), *retained]
        await self._settings.set_sensitive(ASSISTANT_ASSERTION_KEYRING_REF, next_ring)
        return next_ring

    async def jwks(self, *, now: int | None = None) -> dict[str, Any]:
        selected_now = int(time.time()) if now is None else int(now)
        keys = []
        for key in await self.ensure_keyring():
            if not bool(key.get("active")) and int(key.get("verify_until") or 0) < selected_now:
                continue
            keys.append(
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "use": "sig",
                    "alg": "EdDSA",
                    "kid": str(key["kid"]),
                    "x": str(key["public_key"]),
                }
            )
        return {"keys": keys}


class AssistantAssertionService:
    def __init__(self, settings: SettingsStore, keys: AssistantAssertionKeyStore | None = None) -> None:
        self._settings = settings
        self.keys = keys or AssistantAssertionKeyStore(settings)

    async def authorization_epochs(
        self,
        *,
        user_id: str | None,
        device_id: str | None,
        node_id: str,
        household_id: str | None,
    ) -> dict[str, int | None]:
        raw = await self._settings.get(ASSISTANT_AUTHORIZATION_EPOCHS_REF)
        epochs = raw if isinstance(raw, dict) else {}

        def current(kind: str, identifier: str | None) -> int | None:
            if not identifier:
                return None
            values = epochs.get(kind)
            return int(values.get(identifier) or 0) if isinstance(values, dict) else 0

        return {
            "user": current("user", user_id),
            "device": current("device", device_id),
            "node": current("node", node_id) or 0,
            "household": current("household", household_id),
        }

    async def bump_authorization_epoch(self, *, kind: Literal["user", "device", "node", "household"], identifier: str) -> int:
        key = str(identifier or "").strip()
        if not key:
            raise AssistantAssertionError("authorization_epoch_identifier_required")
        raw = await self._settings.get(ASSISTANT_AUTHORIZATION_EPOCHS_REF)
        epochs = dict(raw) if isinstance(raw, dict) else {}
        values = dict(epochs.get(kind) or {})
        values[key] = int(values.get(key) or 0) + 1
        epochs[kind] = values
        await self._settings.set(ASSISTANT_AUTHORIZATION_EPOCHS_REF, epochs)
        return int(values[key])

    async def _sign_claims(self, claims: dict[str, Any]) -> str:
        key = await self.keys.active_key()
        header = {"alg": "EdDSA", "typ": "JWT", "kid": str(key["kid"])}
        signing_input = f"{_b64url_encode(_json_bytes(header))}.{_b64url_encode(_json_bytes(claims))}"
        private_key = Ed25519PrivateKey.from_private_bytes(_b64url_decode(str(key["private_key"])))
        token = f"{signing_input}.{_b64url_encode(private_key.sign(signing_input.encode('ascii')))}"
        await self.keys.record_expiry(kid=str(key["kid"]), exp=int(claims["exp"]))
        return token

    async def issue_actor_assertion(
        self,
        *,
        core_id: str,
        audience: str,
        requester_node_id: str,
        conversation_id: str,
        turn_id: str,
        actor_kind: Literal["human_user", "person", "anonymous"],
        identity_state: Literal["verified", "probable", "unknown", "conflicted"],
        scopes: list[str],
        user_id: str | None = None,
        person_id: str | None = None,
        household_id: str | None = None,
        device_id: str | None = None,
        room_id: str | None = None,
        endpoint_id: str | None = None,
        confidence: float | None = None,
        evidence: list[dict[str, Any]] | None = None,
        now: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        selected_now = int(time.time()) if now is None else int(now)
        clean_scopes = sorted({str(item).strip() for item in scopes if str(item).strip()})
        if not clean_scopes:
            raise AssistantAssertionError("assistant_scope_required")
        if actor_kind == "human_user" and (identity_state != "verified" or not user_id):
            raise AssistantAssertionError("verified_user_required")
        if actor_kind == "person" and not person_id:
            raise AssistantAssertionError("person_id_required")
        if actor_kind == "anonymous" and (user_id or person_id):
            raise AssistantAssertionError("anonymous_identity_must_not_include_ids")
        if confidence is not None and not 0 <= float(confidence) <= 1:
            raise AssistantAssertionError("actor_confidence_invalid")
        subject_id = user_id if actor_kind == "human_user" else person_id if actor_kind == "person" else secrets.token_urlsafe(12)
        exp = selected_now + ASSISTANT_ASSERTION_TTL_SECONDS
        epochs = await self.authorization_epochs(
            user_id=user_id,
            device_id=device_id,
            node_id=requester_node_id,
            household_id=household_id,
        )
        claims: dict[str, Any] = {
            "iss": core_id,
            "aud": audience,
            "sub": f"actor:{actor_kind.replace('human_user', 'user')}:{subject_id}",
            "iat": selected_now,
            "nbf": selected_now,
            "exp": exp,
            "jti": secrets.token_urlsafe(24),
            "core_id": core_id,
            "household_id": household_id,
            "requester_node_id": requester_node_id,
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "actor": {
                "kind": actor_kind,
                "identity_state": identity_state,
                "user_id": user_id,
                "person_id": person_id,
                "confidence": confidence,
                "evidence": list(evidence or []),
            },
            "scope": clean_scopes,
            "constraints": {"room_id": room_id, "endpoint_id": endpoint_id, "device_id": device_id},
            "authorization_epochs": epochs,
        }
        return await self._sign_claims(claims), claims

    async def issue_approval_assertion(
        self,
        *,
        actor_claims: dict[str, Any],
        approval_id: str,
        action: str,
        intent_id: str,
        intent_revision: str,
        canonical_arguments_hash: str,
        target_capability: str,
        correlation_id: str,
        now: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if len(canonical_arguments_hash) != 64 or any(character not in "0123456789abcdefABCDEF" for character in canonical_arguments_hash):
            raise AssistantAssertionError("approval_arguments_hash_invalid")
        selected_now = int(time.time()) if now is None else int(now)
        claims = dict(actor_claims)
        claims.update(
            {
                "iat": selected_now,
                "nbf": selected_now,
                "exp": selected_now + ASSISTANT_ASSERTION_TTL_SECONDS,
                "jti": secrets.token_urlsafe(24),
                "approval": {
                    "approval_id": str(approval_id),
                    "action": str(action),
                    "intent_id": str(intent_id),
                    "intent_revision": str(intent_revision),
                    "canonical_arguments_hash": canonical_arguments_hash.lower(),
                    "target_capability": str(target_capability),
                    "correlation_id": str(correlation_id),
                },
            }
        )
        if any(not str(claims["approval"][field]).strip() for field in ("approval_id", "action", "intent_id", "intent_revision", "target_capability", "correlation_id")):
            raise AssistantAssertionError("approval_binding_required")
        return await self._sign_claims(claims), claims

    async def introspect(
        self,
        token: str,
        *,
        audience: str,
        issuer: str,
        requester_node_id: str,
        conversation_id: str,
        turn_id: str,
        required_scopes: list[str] | None = None,
        consume_approval: bool = False,
        now: int | None = None,
    ) -> dict[str, Any]:
        selected_now = int(time.time()) if now is None else int(now)
        claims = verify_assistant_assertion(
            token,
            jwks=await self.keys.jwks(now=selected_now),
            audience=audience,
            issuer=issuer,
            requester_node_id=requester_node_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            required_scopes=required_scopes,
            now=selected_now,
        )
        actor = claims.get("actor") if isinstance(claims.get("actor"), dict) else {}
        constraints = claims.get("constraints") if isinstance(claims.get("constraints"), dict) else {}
        current_epochs = await self.authorization_epochs(
            user_id=str(actor.get("user_id") or "") or None,
            device_id=str(constraints.get("device_id") or "") or None,
            node_id=requester_node_id,
            household_id=str(claims.get("household_id") or "") or None,
        )
        if claims.get("authorization_epochs") != current_epochs:
            raise AssistantAssertionError("actor_assertion_revoked")
        if consume_approval:
            if not isinstance(claims.get("approval"), dict):
                raise AssistantAssertionError("approval_assertion_required")
            await self._consume_approval(str(claims.get("jti") or ""), exp=int(claims["exp"]), now=selected_now)
        return claims

    async def _consume_approval(self, jti: str, *, exp: int, now: int) -> None:
        if not jti:
            raise AssistantAssertionError("approval_jti_required")
        raw = await self._settings.get(ASSISTANT_CONSUMED_APPROVALS_REF)
        consumed = {
            str(key): int(value)
            for key, value in dict(raw or {}).items()
            if int(value) + ASSISTANT_ASSERTION_CLOCK_SKEW_SECONDS >= now
        }
        if jti in consumed:
            raise AssistantAssertionError("approval_assertion_replayed")
        consumed[jti] = int(exp)
        await self._settings.set(ASSISTANT_CONSUMED_APPROVALS_REF, consumed)

    async def issue_intent_execution_reference(
        self,
        *,
        actor_claims: dict[str, Any],
        owner_node_id: str,
        owner_audience: str,
        intent_id: str,
        contract_version: str,
        intent_revision: str,
        action: str,
        target_capability: str,
        canonical_arguments_hash: str,
        correlation_id: str,
        required_scopes: list[str],
        effective_scopes: list[str],
        now: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if len(canonical_arguments_hash) != 64 or any(character not in "0123456789abcdefABCDEF" for character in canonical_arguments_hash):
            raise AssistantAssertionError("intent_execution_arguments_hash_invalid")
        selected_now = int(time.time()) if now is None else int(now)
        actor = actor_claims.get("actor") if isinstance(actor_claims.get("actor"), dict) else {}
        required = sorted({str(item).strip() for item in required_scopes if str(item).strip()})
        effective = sorted({str(item).strip() for item in effective_scopes if str(item).strip()})
        if any(scope not in effective for scope in required):
            raise AssistantAssertionError("intent_execution_scope_insufficient")
        values = {
            "owner_node_id": owner_node_id,
            "owner_audience": owner_audience,
            "requester_node_id": str(actor_claims.get("requester_node_id") or ""),
            "actor_id": str(actor_claims.get("sub") or ""),
            "identity_state": str(actor.get("identity_state") or "unknown"),
            "conversation_id": str(actor_claims.get("conversation_id") or ""),
            "turn_id": str(actor_claims.get("turn_id") or ""),
            "intent_id": intent_id,
            "contract_version": contract_version,
            "intent_revision": intent_revision,
            "action": action,
            "target_capability": target_capability,
            "canonical_arguments_hash": canonical_arguments_hash.lower(),
            "correlation_id": correlation_id,
        }
        if any(not str(value).strip() for value in values.values()):
            raise AssistantAssertionError("intent_execution_binding_required")
        reference = f"ixr_{secrets.token_urlsafe(32)}"
        digest = hashlib.sha256(reference.encode("utf-8")).hexdigest()
        record = {
            **values,
            "required_scopes": required,
            "effective_scopes": effective,
            "authorization_epochs": actor_claims.get("authorization_epochs"),
            "actor_user_id": actor.get("user_id"),
            "actor_person_id": actor.get("person_id"),
            "actor_household_id": actor_claims.get("household_id"),
            "actor_device_id": (actor_claims.get("constraints") or {}).get("device_id") if isinstance(actor_claims.get("constraints"), dict) else None,
            "issued_at": selected_now,
            "expires_at": selected_now + ASSISTANT_ASSERTION_TTL_SECONDS,
            "consumed_at": None,
        }
        raw = await self._settings.get_sensitive(ASSISTANT_INTENT_EXECUTIONS_REF)
        records = {str(key): value for key, value in dict(raw or {}).items() if isinstance(value, dict) and int(value.get("expires_at") or 0) + ASSISTANT_ASSERTION_CLOCK_SKEW_SECONDS >= selected_now}
        records[digest] = record
        await self._settings.set_sensitive(ASSISTANT_INTENT_EXECUTIONS_REF, records)
        return reference, record

    async def introspect_intent_execution_reference(
        self,
        reference: str,
        *,
        owner_node_id: str,
        bindings: dict[str, str],
        consume: bool = True,
        now: int | None = None,
    ) -> dict[str, Any]:
        selected_now = int(time.time()) if now is None else int(now)
        digest = hashlib.sha256(str(reference).encode("utf-8")).hexdigest()
        raw = await self._settings.get_sensitive(ASSISTANT_INTENT_EXECUTIONS_REF)
        records = dict(raw or {})
        record = records.get(digest)
        if not isinstance(record, dict):
            raise AssistantAssertionError("intent_execution_reference_unknown")
        if int(record.get("expires_at") or 0) <= selected_now:
            raise AssistantAssertionError("intent_execution_reference_expired")
        if record.get("owner_node_id") != owner_node_id:
            raise AssistantAssertionError("intent_execution_owner_mismatch")
        if any(str(record.get(key) or "") != str(value or "") for key, value in bindings.items()):
            raise AssistantAssertionError("intent_execution_binding_mismatch")
        current_epochs = await self.authorization_epochs(
            user_id=str(record.get("actor_user_id") or "") or None,
            device_id=str(record.get("actor_device_id") or "") or None,
            node_id=str(record.get("requester_node_id") or ""),
            household_id=str(record.get("actor_household_id") or "") or None,
        )
        expected_epochs = record.get("authorization_epochs") if isinstance(record.get("authorization_epochs"), dict) else {}
        if current_epochs != expected_epochs:
            raise AssistantAssertionError("intent_execution_authorization_revoked")
        replayed = record.get("consumed_at") is not None
        if consume and not replayed:
            record["consumed_at"] = selected_now
            records[digest] = record
            await self._settings.set_sensitive(ASSISTANT_INTENT_EXECUTIONS_REF, records)
        return {**record, "replayed": replayed}

    async def issue_speaker_enrollment_grant(
        self,
        *,
        node_id: str,
        person_id: str,
        household_id: str,
        endpoint_id: str,
        enrollment_session_id: str,
        now: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        selected_now = int(time.time()) if now is None else int(now)
        reference = f"seg_{secrets.token_urlsafe(32)}"
        digest = hashlib.sha256(reference.encode("utf-8")).hexdigest()
        record = {
            "node_id": node_id, "person_id": person_id, "household_id": household_id,
            "endpoint_id": endpoint_id, "enrollment_session_id": enrollment_session_id,
            "purpose": "speaker-recognition", "issued_at": selected_now,
            "expires_at": selected_now + 120, "consumed_at": None,
        }
        raw = await self._settings.get_sensitive(ASSISTANT_ENROLLMENT_GRANTS_REF)
        records = {str(key): value for key, value in dict(raw or {}).items() if isinstance(value, dict) and int(value.get("expires_at") or 0) + ASSISTANT_ASSERTION_CLOCK_SKEW_SECONDS >= selected_now}
        records[digest] = record
        await self._settings.set_sensitive(ASSISTANT_ENROLLMENT_GRANTS_REF, records)
        return reference, record

    async def consume_speaker_enrollment_grant(self, reference: str, *, bindings: dict[str, str], now: int | None = None) -> dict[str, Any]:
        selected_now = int(time.time()) if now is None else int(now)
        digest = hashlib.sha256(str(reference).encode("utf-8")).hexdigest()
        raw = await self._settings.get_sensitive(ASSISTANT_ENROLLMENT_GRANTS_REF)
        records = dict(raw or {})
        record = records.get(digest)
        if not isinstance(record, dict):
            raise AssistantAssertionError("speaker_enrollment_grant_unknown")
        if int(record.get("expires_at") or 0) <= selected_now:
            raise AssistantAssertionError("speaker_enrollment_grant_expired")
        if any(str(record.get(key) or "") != str(value or "") for key, value in bindings.items()):
            raise AssistantAssertionError("speaker_enrollment_grant_binding_mismatch")
        if record.get("consumed_at") is not None:
            raise AssistantAssertionError("speaker_enrollment_grant_replayed")
        record["consumed_at"] = selected_now
        records[digest] = record
        await self._settings.set_sensitive(ASSISTANT_ENROLLMENT_GRANTS_REF, records)
        return record


def verify_assistant_assertion(
    token: str,
    *,
    jwks: dict[str, Any],
    audience: str,
    issuer: str,
    requester_node_id: str,
    conversation_id: str,
    turn_id: str,
    required_scopes: list[str] | None = None,
    now: int | None = None,
) -> dict[str, Any]:
    try:
        h64, p64, s64 = token.split(".")
        header = json.loads(_b64url_decode(h64))
        claims = json.loads(_b64url_decode(p64))
    except Exception as exc:
        raise AssistantAssertionError("actor_assertion_malformed") from exc
    if header.get("alg") != "EdDSA" or not str(header.get("kid") or ""):
        raise AssistantAssertionError("actor_assertion_header_invalid")
    key = next((item for item in list(jwks.get("keys") or []) if item.get("kid") == header["kid"]), None)
    if not isinstance(key, dict) or key.get("kty") != "OKP" or key.get("crv") != "Ed25519":
        raise AssistantAssertionError("actor_assertion_key_unknown")
    try:
        Ed25519PublicKey.from_public_bytes(_b64url_decode(str(key["x"]))).verify(
            _b64url_decode(s64), f"{h64}.{p64}".encode("ascii")
        )
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise AssistantAssertionError("actor_assertion_signature_invalid") from exc
    selected_now = int(time.time()) if now is None else int(now)
    expected = {
        "iss": issuer,
        "aud": audience,
        "requester_node_id": requester_node_id,
        "conversation_id": conversation_id,
        "turn_id": turn_id,
    }
    if any(claims.get(name) != value for name, value in expected.items()):
        raise AssistantAssertionError("actor_assertion_binding_invalid")
    if int(claims.get("nbf") or 0) > selected_now + ASSISTANT_ASSERTION_CLOCK_SKEW_SECONDS:
        raise AssistantAssertionError("actor_assertion_not_yet_valid")
    if int(claims.get("exp") or 0) <= selected_now:
        raise AssistantAssertionError("actor_assertion_expired")
    scopes = {str(item) for item in list(claims.get("scope") or [])}
    if any(scope not in scopes for scope in list(required_scopes or [])):
        raise AssistantAssertionError("actor_assertion_scope_insufficient")
    return claims
