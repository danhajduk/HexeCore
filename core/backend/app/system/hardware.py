from __future__ import annotations

import json
import hashlib
import os
import socket
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.system.auth.tokens import ServiceTokenError, sign_hs256, validate_claims, verify_hs256

HARDWARE_ACCESS_SCHEMA_VERSION = "1"
HARDWARE_LEASE_AUDIENCE = "hexe.hardware.bluetooth"
BLE_PAIRING_ADVERT_OPERATION = "ble.host_pairing_advert"
BLE_PAIRING_ADVERT_SCOPE = f"hardware.bluetooth.{BLE_PAIRING_ADVERT_OPERATION}"
BLE_PROVISIONING_CONTRACT_VERSION = "1.0"
BLE_PROVISIONING_ENVELOPE_SCHEMA_VERSION = "1.0"
BLE_PROVISIONING_ENCRYPTION_ALGORITHM = "aes-256-gcm"
BLE_PROVISIONING_KEY_AGREEMENT = "x25519-hkdf-sha256"
VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID = "hexe.voice_node.wifi_backend.v1"
SUPPORTED_HARDWARE_RESOURCES = {"bluetooth"}
SUPPORTED_BLUETOOTH_OPERATIONS = {"ble.status", "ble.scan", "ble.read_identity", "ble.provision_wifi", BLE_PAIRING_ADVERT_OPERATION}

VOICE_WIFI_PROVISIONING_PAYLOAD_SCHEMA: dict[str, Any] = {
    "schema_id": VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID,
    "json_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["wifi_ssid", "backend_host", "http_port", "ws_port", "use_tls"],
        "properties": {
            "wifi_ssid": {"type": "string", "minLength": 1, "maxLength": 32},
            "wifi_password": {"anyOf": [{"type": "string", "minLength": 8, "maxLength": 63}, {"type": "null"}]},
            "backend_host": {"type": "string", "minLength": 1, "maxLength": 253},
            "http_port": {"type": "integer", "minimum": 1, "maximum": 65535},
            "ws_port": {"type": "integer", "minimum": 1, "maximum": 65535},
            "use_tls": {"type": "boolean", "default": True},
            "endpoint_name": {"anyOf": [{"type": "string", "minLength": 1, "maxLength": 64}, {"type": "null"}]},
            "display_name": {"anyOf": [{"type": "string", "minLength": 1, "maxLength": 80}, {"type": "null"}]},
        },
    },
}
PROVISIONING_PAYLOAD_SCHEMAS = {"voice": VOICE_WIFI_PROVISIONING_PAYLOAD_SCHEMA}

BLE_PROVISIONING_ENVELOPE_SCHEMA: dict[str, Any] = {
    "schema_id": "hexe.ble_onboarding.provisioning_envelope.v1",
    "json_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "payload_schema_id",
            "contract_version",
            "onboarding_session_id",
            "target_node_id",
            "pairing_nonce",
            "sequence",
            "expires_at",
            "algorithm",
            "key_agreement",
            "key_id",
            "supervisor_ephemeral_public_key",
            "nonce",
            "aad",
            "ciphertext",
            "tag",
        ],
        "properties": {
            "schema_version": {"const": BLE_PROVISIONING_ENVELOPE_SCHEMA_VERSION},
            "payload_schema_id": {"type": "string", "minLength": 1},
            "contract_version": {"const": BLE_PROVISIONING_CONTRACT_VERSION},
            "onboarding_session_id": {"type": "string", "minLength": 1},
            "device_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "target_node_id": {"type": "string", "minLength": 1},
            "pairing_nonce": {"type": "string", "minLength": 8, "maxLength": 128},
            "sequence": {"type": "integer", "minimum": 1},
            "expires_at": {"type": "string", "format": "date-time"},
            "algorithm": {"const": BLE_PROVISIONING_ENCRYPTION_ALGORITHM},
            "key_agreement": {"const": BLE_PROVISIONING_KEY_AGREEMENT},
            "key_id": {"type": "string", "minLength": 16},
            "supervisor_ephemeral_public_key": {"type": "string", "minLength": 43, "maxLength": 128},
            "nonce": {"type": "string", "minLength": 16},
            "aad": {"type": "string", "minLength": 16},
            "ciphertext": {"type": "string", "minLength": 1},
            "tag": {"type": "string", "minLength": 16},
        },
    },
}

BLE_CORE_PUBLISHED_PAIRING_SESSION_SCHEMA: dict[str, Any] = {
    "schema_id": "hexe.ble_onboarding.core_published_pairing.v1",
    "service_uuid": "7f9c0000-5f04-4d8b-9a46-7c0f7a100000",
    "advertisement_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["contract_version", "session_role", "session_hint"],
        "properties": {
            "contract_version": {"const": BLE_PROVISIONING_CONTRACT_VERSION},
            "session_role": {"const": "host_pairing_advert"},
            "session_hint": {"type": "string", "minLength": 6, "maxLength": 32},
            "expires_at": {"type": "string", "format": "date-time"},
            "capability_flags": {"type": "array", "items": {"type": "string", "minLength": 1}},
        },
    },
    "pairing_offer_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "contract_version",
            "onboarding_session_id",
            "session_role",
            "session_hint",
            "supervisor_id",
            "expires_at",
            "requested_profile",
            "payload_schema_id",
            "claim_code_required",
        ],
        "properties": {
            "contract_version": {"const": BLE_PROVISIONING_CONTRACT_VERSION},
            "onboarding_session_id": {"type": "string", "minLength": 1},
            "session_role": {"const": "host_pairing_advert"},
            "session_hint": {"type": "string", "minLength": 6, "maxLength": 32},
            "supervisor_id": {"type": "string", "minLength": 1},
            "core_id": {"type": "string", "minLength": 1},
            "expires_at": {"type": "string", "format": "date-time"},
            "requested_profile": {"const": "voice"},
            "payload_schema_id": {"const": VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID},
            "claim_code_required": {"type": "boolean"},
        },
    },
    "endpoint_identity_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "contract_version",
            "onboarding_session_id",
            "device_id",
            "node_hardware_id",
            "target_node_id",
            "board_profile",
            "firmware_version",
            "application_type",
            "provisioning_mode",
            "endpoint_ephemeral_public_key",
            "supported_payload_schemas",
            "provisioning_state",
        ],
        "properties": {
            "contract_version": {"const": BLE_PROVISIONING_CONTRACT_VERSION},
            "onboarding_session_id": {"type": "string", "minLength": 1},
            "device_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "node_hardware_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "target_node_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "board_profile": {"type": "string", "minLength": 1, "maxLength": 80},
            "firmware_version": {"type": "string", "minLength": 1, "maxLength": 120},
            "application_type": {"type": "string", "minLength": 1, "maxLength": 80},
            "provisioning_mode": {"type": "string", "minLength": 1, "maxLength": 80},
            "endpoint_ephemeral_public_key": {"type": "string", "minLength": 43, "maxLength": 128},
            "supported_payload_schemas": {"type": "array", "items": {"type": "string", "minLength": 1}},
            "provisioning_state": {"type": "string", "minLength": 1, "maxLength": 80},
        },
    },
    "wifi_handoff_required_fields": ["onboarding_session_id", "device_id"],
}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_ts() -> int:
    return int(time.time())


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def clean_text(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def bluetooth_access_policy(value: object | None = None) -> str:
    text = clean_text(value or os.getenv("HEXE_BLUETOOTH_ACCESS_POLICY"), "disabled").lower()
    if text in {"disabled", "ask", "trusted_only", "allowed"}:
        return text
    return "disabled"


def hardware_lease_ttl_s(value: object | None = None) -> int:
    raw = clean_text(value or os.getenv("HEXE_HARDWARE_LEASE_TTL_S"), "600")
    try:
        return min(max(int(float(raw)), 30), 24 * 60 * 60)
    except Exception:
        return 600


def hardware_lease_secret() -> str:
    return clean_text(os.getenv("HEXE_HARDWARE_LEASE_SECRET"))


def freshness_state(record: object) -> str:
    from app.system.supervisors import _freshness_state

    return str(_freshness_state(getattr(record, "last_seen_at", None)))


def supervisor_bluetooth_policy(record: object) -> str:
    metadata = getattr(record, "metadata", {}) if record is not None else {}
    bluetooth = metadata.get("bluetooth") if isinstance(metadata, dict) else None
    policy = bluetooth.get("policy") if isinstance(bluetooth, dict) else None
    return bluetooth_access_policy(policy)


def supervisor_has_bluetooth(record: object) -> bool:
    resources = getattr(record, "resources", {}) if record is not None else {}
    capabilities = getattr(record, "capabilities", []) if record is not None else []
    return bool(
        isinstance(resources, dict)
        and resources.get("bluetooth_present")
        and isinstance(capabilities, list)
        and "bluetooth_governance" in [str(item) for item in capabilities]
    )


def supervisor_broker_url(record: object) -> str | None:
    base = clean_text(getattr(record, "api_base_url", None)).rstrip("/")
    if not base:
        return None
    return f"{base}/api/supervisor/hardware/bluetooth/ble"


def active_bluetooth_supervisors(supervisor_store: object | None) -> list[object]:
    if supervisor_store is None or not hasattr(supervisor_store, "list"):
        return []
    records = supervisor_store.list(include_historical=False)
    candidates = [
        record
        for record in records
        if supervisor_has_bluetooth(record)
        and clean_text(getattr(record, "trust_status", "")).lower() == "trusted"
        and freshness_state(record) == "online"
    ]
    candidates.sort(
        key=lambda record: (
            clean_text(getattr(record, "host_id", "")).lower() == socket.gethostname().lower()
            or clean_text(getattr(record, "hostname", "")).lower() == socket.gethostname().lower(),
            "local_core_attached" in [str(item) for item in getattr(record, "capabilities", []) or []],
            clean_text(getattr(record, "transport", "")).lower() == "local",
            clean_text(getattr(record, "last_seen_at", "")),
        ),
        reverse=True,
    )
    return candidates


class HardwareProvisioningContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"] = Field(default=BLE_PROVISIONING_CONTRACT_VERSION)
    schema_version: Literal["1.0"] = Field(default=BLE_PROVISIONING_ENVELOPE_SCHEMA_VERSION)
    onboarding_session_id: str = Field(..., min_length=1)
    target_node_id: str = Field(..., min_length=1)
    node_profile_id: str = Field(default="voice", min_length=1)
    payload_schema_id: str = Field(default=VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID, min_length=1)
    endpoint_ephemeral_public_key: str = Field(..., min_length=43, max_length=128)
    pairing_nonce: str | None = Field(default=None, min_length=8, max_length=128)
    claim_code_ref: str | None = Field(default=None, min_length=1, max_length=128)
    sequence: int = Field(default=1, ge=1)
    expires_at: str | None = Field(default=None, description="UTC ISO-8601 expiry for the pairing nonce/envelope replay window.")

    @model_validator(mode="after")
    def _validate_binding(self):
        if not clean_text(self.pairing_nonce) and not clean_text(self.claim_code_ref):
            raise ValueError("pairing_nonce_or_claim_code_ref_required")
        if self.node_profile_id == "voice" and self.payload_schema_id != VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID:
            raise ValueError("unsupported_voice_provisioning_payload_schema")
        if self.node_profile_id not in PROVISIONING_PAYLOAD_SCHEMAS:
            raise ValueError("unsupported_node_provisioning_profile")
        if clean_text(self.expires_at):
            try:
                expires = datetime.fromisoformat(str(self.expires_at).replace("Z", "+00:00"))
            except Exception:
                raise ValueError("provisioning_expires_at_invalid") from None
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= datetime.now(timezone.utc):
                raise ValueError("provisioning_expires_at_expired")
        return self


class HardwareAccessRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1, description="Trusted node id requesting hardware access.")
    resource_type: Literal["bluetooth"] = Field(default="bluetooth", description="Host hardware resource type.")
    operation: Literal["ble.status", "ble.scan", "ble.read_identity", "ble.provision_wifi", "ble.host_pairing_advert"] = Field(
        default="ble.scan",
        description="Bluetooth operation the node is requesting a Core-governed lease for.",
    )
    supervisor_id: str | None = Field(default=None, description="Optional target Supervisor id.")
    adapter: str | None = Field(default=None, description="Optional Bluetooth adapter id such as hci0.")
    duration_s: int | None = Field(
        default=None,
        ge=30,
        le=24 * 60 * 60,
        description="Optional requested lease duration in seconds.",
    )
    reason: str | None = Field(default=None, description="Optional operator-readable reason for the request.")
    provisioning: HardwareProvisioningContext | None = Field(
        default=None,
        description="Required only for ble.provision_wifi; carries session/profile binding without plaintext credentials.",
    )

    @model_validator(mode="after")
    def _validate_provisioning_context(self):
        if self.operation == "ble.provision_wifi" and self.provisioning is None:
            raise ValueError("provisioning_context_required")
        if self.operation != "ble.provision_wifi" and self.provisioning is not None:
            raise ValueError("provisioning_context_only_supported_for_ble_provision_wifi")
        return self


class HardwareAccessDecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "deny"]
    reason: str | None = None
    duration_s: int | None = Field(default=None, ge=30, le=24 * 60 * 60)


class HardwareLeaseReleaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1)


class HardwareLeaseValidationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1)
    lease_token: str = Field(..., min_length=1)
    resource_type: Literal["bluetooth"] = "bluetooth"
    operation: Literal["ble.status", "ble.scan", "ble.read_identity", "ble.provision_wifi", "ble.host_pairing_advert"] = "ble.scan"
    supervisor_id: str | None = None
    adapter: str | None = None
    provisioning: HardwareProvisioningContext | None = None


class HardwareBleScanRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1, description="Trusted node id requesting a Core-governed BLE scan.")
    supervisor_id: str | None = Field(default=None, max_length=120, description="Optional supervisor filter.")
    adapter: str | None = Field(default=None, max_length=64, description="Optional Bluetooth adapter id such as hci0.")
    service_uuid: str | None = Field(default=None, min_length=4, max_length=64, description="Optional BLE service UUID to match.")
    scan_seconds: int = Field(default=5, ge=1, le=60, description="BLE scan duration requested from each supervisor.")
    reason: str | None = Field(default=None, max_length=240, description="Optional operator-readable reason for the fleet scan.")


class HardwareOperatorBleScanRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supervisor_id: str | None = Field(default=None, max_length=120, description="Optional supervisor filter.")
    adapter: str | None = Field(default=None, max_length=64, description="Optional Bluetooth adapter id such as hci0.")
    service_uuid: str | None = Field(default=None, min_length=4, max_length=64, description="Optional BLE service UUID to match.")
    scan_seconds: int = Field(default=5, ge=1, le=60, description="BLE scan duration requested from each supervisor.")
    reason: str | None = Field(default=None, max_length=240, description="Optional operator-readable reason for the fleet scan.")


class HardwareBleIdentityRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1, description="Trusted node id requesting Core-governed BLE onboarding identity.")
    supervisor_id: str | None = Field(default=None, max_length=120, description="Optional supervisor filter.")
    adapter: str | None = Field(default=None, max_length=64, description="Optional Bluetooth adapter id such as hci0.")
    target_address: str = Field(..., min_length=1, max_length=64, description="BLE device address to connect and read.")
    timeout_s: int = Field(default=20, ge=1, le=60, description="BLE GATT identity read timeout requested from each supervisor.")
    reason: str | None = Field(default=None, max_length=240, description="Optional operator-readable reason for the identity read.")


class HardwareBlePairingSessionCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supervisor_id: str | None = Field(default=None, max_length=120, description="Optional supervisor filter.")
    adapter: str | None = Field(default=None, max_length=64, description="Optional Bluetooth adapter id such as hci0.")
    duration_s: int = Field(default=300, ge=60, le=600, description="Pairing session lifetime in seconds.")
    node_profile_id: Literal["voice"] = Field(default="voice", description="Target endpoint profile.")
    payload_schema_id: Literal["hexe.voice_node.wifi_backend.v1"] = Field(default=VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID)
    claim_code_required: bool = False
    reason: str | None = Field(default=None, max_length=240)


class HardwareNodeBlePairingSessionCreateBody(HardwareBlePairingSessionCreateBody):
    node_id: str = Field(..., min_length=1, description="Trusted node id requesting a Core-governed BLE pairing session.")


class HardwareBlePairingSessionCancelBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=240)


class HardwareBlePairingSessionApproveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=240)


class HardwareNodeBlePairingSessionApproveBody(HardwareBlePairingSessionApproveBody):
    node_id: str = Field(..., min_length=1)


class HardwareNodeBlePairingSessionCancelBody(HardwareBlePairingSessionCancelBody):
    node_id: str = Field(..., min_length=1)


def hardware_access_request_schema_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "schema_version": HARDWARE_ACCESS_SCHEMA_VERSION,
        "resource_types": sorted(SUPPORTED_HARDWARE_RESOURCES),
        "operations": sorted(SUPPORTED_BLUETOOTH_OPERATIONS),
        "request_schema": HardwareAccessRequestBody.model_json_schema(),
        "provisioning_payload_schemas": PROVISIONING_PAYLOAD_SCHEMAS,
        "provisioning_envelope_schema": BLE_PROVISIONING_ENVELOPE_SCHEMA,
        "core_published_pairing_session_schema": BLE_CORE_PUBLISHED_PAIRING_SESSION_SCHEMA,
        "encryption_model": {
            "key_agreement": BLE_PROVISIONING_KEY_AGREEMENT,
            "algorithm": BLE_PROVISIONING_ENCRYPTION_ALGORITHM,
            "replay_protection": ["sequence", "expires_at"],
            "redacted_fields": ["wifi_password", "claim_code", "derived_key", "ciphertext", "tag", "decrypted_payload"],
        },
    }


def hardware_ble_provisioning_schema_payload(node_profile_id: str = "voice") -> dict[str, Any]:
    profile_key = clean_text(node_profile_id, "voice").lower()
    schema = PROVISIONING_PAYLOAD_SCHEMAS.get(profile_key)
    if schema is None:
        raise KeyError("unsupported_node_provisioning_profile")
    return {
        "ok": True,
        "contract_version": BLE_PROVISIONING_CONTRACT_VERSION,
        "schema_version": BLE_PROVISIONING_ENVELOPE_SCHEMA_VERSION,
        "operation": "ble.provision_wifi",
        "node_profile_id": profile_key,
        "payload_schema": schema,
        "provisioning_envelope_schema": BLE_PROVISIONING_ENVELOPE_SCHEMA,
        "core_published_pairing_session_schema": BLE_CORE_PUBLISHED_PAIRING_SESSION_SCHEMA,
        "encryption_model": {
            "key_agreement": BLE_PROVISIONING_KEY_AGREEMENT,
            "algorithm": BLE_PROVISIONING_ENCRYPTION_ALGORITHM,
            "endpoint_public_key": "endpoint_ephemeral_public_key",
            "supervisor_public_key": "supervisor_ephemeral_public_key",
            "replay_protection": ["sequence", "expires_at"],
        },
    }


@dataclass
class HardwareBlePairingSessionRecord:
    session_id: str
    session_hint: str
    status: str
    node_profile_id: str
    payload_schema_id: str
    claim_code_required: bool
    created_at: str
    updated_at: str
    expires_at: str
    requesting_node_id: str | None = None
    supervisor_id: str | None = None
    adapter: str | None = None
    reason: str | None = None
    approved_device_id: str | None = None
    approved_at: str | None = None
    canceled_at: str | None = None
    consumed_at: str | None = None
    error: str | None = None
    endpoint_identity: dict[str, Any] | None = None
    supervisor_results: list[dict[str, Any]] = field(default_factory=list)
    audit: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "session_id": self.session_id,
            "session_hint": self.session_hint,
            "status": self.status,
            "node_profile_id": self.node_profile_id,
            "payload_schema_id": self.payload_schema_id,
            "claim_code_required": self.claim_code_required,
            "supervisor_id": self.supervisor_id,
            "adapter": self.adapter,
            "reason": self.reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "requesting_node_id": self.requesting_node_id,
            "approved_device_id": self.approved_device_id,
            "approved_at": self.approved_at,
            "canceled_at": self.canceled_at,
            "consumed_at": self.consumed_at,
            "error": self.error,
            "endpoint_identity": dict(self.endpoint_identity) if isinstance(self.endpoint_identity, dict) else None,
            "supervisor_results": [dict(item) for item in self.supervisor_results],
            "audit": [dict(item) for item in self.audit],
        }

    def to_api_dict(self, *, include_audit: bool = False) -> dict[str, Any]:
        payload = self.to_dict()
        if not include_audit:
            payload.pop("audit", None)
        return payload


class HardwareBlePairingSessionStore:
    def __init__(self, path: Path | None = None) -> None:
        configured = clean_text(os.getenv("HEXE_BLE_PAIRING_SESSIONS_DB"))
        self._path = path or (Path(configured) if configured else repo_root() / "data" / "ble_pairing_sessions.json")
        self._records: dict[str, HardwareBlePairingSessionRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        items = raw.get("items") if isinstance(raw, dict) and isinstance(raw.get("items"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            session_id = clean_text(item.get("session_id"))
            if not session_id:
                continue
            self._records[session_id] = HardwareBlePairingSessionRecord(
                session_id=session_id,
                session_hint=clean_text(item.get("session_hint")),
                status=clean_text(item.get("status"), "waiting"),
                node_profile_id=clean_text(item.get("node_profile_id"), "voice"),
                payload_schema_id=clean_text(item.get("payload_schema_id"), VOICE_PROVISIONING_PAYLOAD_SCHEMA_ID),
                claim_code_required=bool(item.get("claim_code_required")),
                supervisor_id=clean_text(item.get("supervisor_id")) or None,
                adapter=clean_text(item.get("adapter")) or None,
                reason=clean_text(item.get("reason")) or None,
                created_at=clean_text(item.get("created_at"), utcnow_iso()),
                updated_at=clean_text(item.get("updated_at"), utcnow_iso()),
                expires_at=clean_text(item.get("expires_at"), utcnow_iso()),
                requesting_node_id=clean_text(item.get("requesting_node_id")) or None,
                approved_device_id=clean_text(item.get("approved_device_id")) or None,
                approved_at=clean_text(item.get("approved_at")) or None,
                canceled_at=clean_text(item.get("canceled_at")) or None,
                consumed_at=clean_text(item.get("consumed_at")) or None,
                error=clean_text(item.get("error")) or None,
                endpoint_identity=dict(item.get("endpoint_identity")) if isinstance(item.get("endpoint_identity"), dict) else None,
                supervisor_results=[dict(row) for row in item.get("supervisor_results", []) if isinstance(row, dict)]
                if isinstance(item.get("supervisor_results"), list)
                else [],
                audit=[dict(row) for row in item.get("audit", []) if isinstance(row, dict)] if isinstance(item.get("audit"), list) else [],
            )

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "items": [record.to_dict() for record in sorted(self._records.values(), key=lambda item: item.created_at)],
        }
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def upsert(self, record: HardwareBlePairingSessionRecord) -> HardwareBlePairingSessionRecord:
        self._records[record.session_id] = record
        self._save()
        return record

    def get(self, session_id: str) -> HardwareBlePairingSessionRecord | None:
        return self._records.get(clean_text(session_id))

    def list(self, *, status: str | None = None) -> list[HardwareBlePairingSessionRecord]:
        status_key = clean_text(status).lower()
        records = sorted(self._records.values(), key=lambda item: item.created_at, reverse=True)
        if status_key:
            records = [record for record in records if record.status == status_key]
        return records


class HardwareBlePairingSessionService:
    def __init__(self, store: HardwareBlePairingSessionStore, supervisor_store: object | None) -> None:
        self._store = store
        self._supervisor_store = supervisor_store

    def create_session(
        self,
        body: HardwareBlePairingSessionCreateBody,
        *,
        requesting_node_id: str | None = None,
        allowed_supervisor_ids: set[str] | None = None,
    ) -> HardwareBlePairingSessionRecord:
        self._expire_old_sessions()
        now = datetime.now(timezone.utc)
        session_id = f"blepair_{secrets.token_urlsafe(12)}"
        expires_at = (now + timedelta(seconds=int(body.duration_s))).replace(microsecond=0).isoformat()
        session_hint = secrets.token_urlsafe(6)[:8]
        candidates = active_bluetooth_supervisors(self._supervisor_store)
        if allowed_supervisor_ids is not None:
            candidates = [record for record in candidates if clean_text(getattr(record, "supervisor_id", "")) in allowed_supervisor_ids]
        supervisor_filter = clean_text(body.supervisor_id)
        if supervisor_filter:
            candidates = [record for record in candidates if clean_text(getattr(record, "supervisor_id", "")) == supervisor_filter]
        supervisor_results: list[dict[str, Any]] = []
        for supervisor in candidates:
            policy = supervisor_bluetooth_policy(supervisor)
            supervisor_id = clean_text(getattr(supervisor, "supervisor_id", ""))
            result: dict[str, Any] = {
                "supervisor_id": supervisor_id,
                "status": "pending",
                "adapter": clean_text(body.adapter) or None,
                "policy": policy,
            }
            if policy == "disabled":
                result.update({"status": "failed", "error": "bluetooth_policy_disabled"})
            supervisor_results.append(result)
        status = "waiting" if any(item.get("status") == "pending" for item in supervisor_results) else "failed"
        record = HardwareBlePairingSessionRecord(
            session_id=session_id,
            session_hint=session_hint,
            status=status,
            node_profile_id=body.node_profile_id,
            payload_schema_id=body.payload_schema_id,
            claim_code_required=body.claim_code_required,
            requesting_node_id=clean_text(requesting_node_id) or None,
            supervisor_id=supervisor_filter or None,
            adapter=clean_text(body.adapter) or None,
            reason=clean_text(body.reason) or None,
            created_at=now.replace(microsecond=0).isoformat(),
            updated_at=now.replace(microsecond=0).isoformat(),
            expires_at=expires_at,
            supervisor_results=supervisor_results,
            error=None if supervisor_results else "bluetooth_supervisor_unavailable",
            audit=[{"event": "created", "at": now.replace(microsecond=0).isoformat(), "supervisor_count": len(candidates)}],
        )
        if record.error:
            record.audit.append({"event": "failed", "at": record.updated_at, "reason": record.error})
        return self._store.upsert(record)

    def get_session(self, session_id: str) -> HardwareBlePairingSessionRecord | None:
        self._expire_old_sessions()
        return self._store.get(session_id)

    def list_sessions(self, *, status: str | None = None) -> list[HardwareBlePairingSessionRecord]:
        self._expire_old_sessions()
        return self._store.list(status=status)

    def find_active_session(
        self,
        body: HardwareBlePairingSessionCreateBody,
        *,
        requesting_node_id: str | None = None,
    ) -> HardwareBlePairingSessionRecord | None:
        self._expire_old_sessions()
        requested_node_id = clean_text(requesting_node_id)
        requested_adapter = clean_text(body.adapter)
        requested_supervisor_id = clean_text(body.supervisor_id)
        for record in self._store.list():
            if record.status not in {"waiting", "found", "approved"}:
                continue
            if requested_node_id and clean_text(record.requesting_node_id) != requested_node_id:
                continue
            if clean_text(record.node_profile_id) != clean_text(body.node_profile_id):
                continue
            if clean_text(record.payload_schema_id) != clean_text(body.payload_schema_id):
                continue
            if bool(record.claim_code_required) != bool(body.claim_code_required):
                continue
            if requested_adapter and clean_text(record.adapter) != requested_adapter:
                continue
            if requested_supervisor_id and clean_text(record.supervisor_id) != requested_supervisor_id:
                continue
            return record
        return None

    def pairing_offer(self, record: HardwareBlePairingSessionRecord, *, supervisor_id: str, adapter: str | None) -> dict[str, Any]:
        return {
            "contract_version": BLE_PROVISIONING_CONTRACT_VERSION,
            "onboarding_session_id": record.session_id,
            "session_role": "host_pairing_advert",
            "session_hint": record.session_hint,
            "supervisor_id": supervisor_id,
            "expires_at": record.expires_at,
            "requested_profile": record.node_profile_id,
            "payload_schema_id": record.payload_schema_id,
            "claim_code_required": record.claim_code_required,
            "adapter": adapter,
        }

    def pairing_session_token(self, record: HardwareBlePairingSessionRecord, *, supervisor_id: str, adapter: str | None) -> str:
        secret = hardware_lease_secret()
        if not secret:
            raise RuntimeError("hardware_lease_secret_unconfigured")
        expires = datetime.fromisoformat(record.expires_at.replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        now_ts = utc_ts()
        claims = {
            "sub": "core",
            "aud": HARDWARE_LEASE_AUDIENCE,
            "scp": [BLE_PAIRING_ADVERT_SCOPE],
            "iat": now_ts,
            "exp": int(expires.timestamp()),
            "jti": f"blepairtoken_{secrets.token_urlsafe(12)}",
            "operation": BLE_PAIRING_ADVERT_OPERATION,
            "supervisor_id": supervisor_id,
            "adapter": adapter,
            "onboarding_session_id": record.session_id,
            "session_hint": record.session_hint,
            "payload_schema_id": record.payload_schema_id,
        }
        return sign_hs256({"alg": "HS256", "typ": "JWT", "kid": "hardware-v1"}, claims, secret=secret)

    def update_supervisor_result(self, session_id: str, supervisor_id: str, result: dict[str, Any]) -> HardwareBlePairingSessionRecord:
        record = self._store.get(session_id)
        if record is None:
            raise KeyError("ble_pairing_session_not_found")
        now = utcnow_iso()
        updated = False
        for item in record.supervisor_results:
            if clean_text(item.get("supervisor_id")) == clean_text(supervisor_id):
                item.update({key: value for key, value in result.items() if key != "session_token"})
                updated = True
                break
        if not updated:
            record.supervisor_results.append({key: value for key, value in result.items() if key != "session_token"})
        identity = result.get("endpoint_identity") if isinstance(result.get("endpoint_identity"), dict) else None
        if identity:
            self._apply_endpoint_identity(record, identity, supervisor_id=supervisor_id, at=now)
        elif record.status not in {"found", "approved", "canceled", "expired", "consumed"}:
            supervisor_statuses = {clean_text(item.get("status")).lower() for item in record.supervisor_results}
            if supervisor_statuses & {"advertising", "endpoint_identity_received"}:
                record.status = "waiting"
                record.error = None
            elif "pending" in supervisor_statuses:
                record.status = "waiting"
                record.error = None
            elif record.supervisor_results and supervisor_statuses <= {"failed", "not_found", "stopped", "expired"}:
                record.status = "failed"
                record.error = "ble_pairing_advert_unavailable"
        record.updated_at = now
        record.audit.append({"event": "supervisor_result", "at": now, "supervisor_id": supervisor_id, "status": result.get("status")})
        return self._store.upsert(record)

    def approve(self, session_id: str, body: HardwareBlePairingSessionApproveBody) -> HardwareBlePairingSessionRecord:
        record = self._store.get(session_id)
        if record is None:
            raise KeyError("ble_pairing_session_not_found")
        self._expire_record_if_needed(record)
        if record.status == "expired":
            self._store.upsert(record)
            raise ValueError("ble_pairing_session_expired")
        if record.status in {"canceled", "consumed"}:
            raise ValueError(f"ble_pairing_session_{record.status}")
        identity = record.endpoint_identity if isinstance(record.endpoint_identity, dict) else None
        if not identity:
            raise ValueError("ble_pairing_endpoint_identity_missing")
        device_id = clean_text(body.device_id)
        if clean_text(identity.get("device_id")) != device_id:
            raise ValueError("ble_pairing_device_id_mismatch")
        now = utcnow_iso()
        record.status = "approved"
        record.approved_device_id = device_id
        record.approved_at = now
        record.updated_at = now
        record.audit.append({"event": "approved", "at": now, "device_id": device_id, "reason": clean_text(body.reason) or None})
        return self._store.upsert(record)

    def cancel(self, session_id: str, body: HardwareBlePairingSessionCancelBody) -> HardwareBlePairingSessionRecord:
        record = self._store.get(session_id)
        if record is None:
            raise KeyError("ble_pairing_session_not_found")
        now = utcnow_iso()
        record.status = "canceled"
        record.canceled_at = now
        record.updated_at = now
        record.audit.append({"event": "canceled", "at": now, "reason": clean_text(body.reason) or None})
        return self._store.upsert(record)

    def _apply_endpoint_identity(
        self,
        record: HardwareBlePairingSessionRecord,
        identity: dict[str, Any],
        *,
        supervisor_id: str,
        at: str,
    ) -> None:
        if clean_text(identity.get("onboarding_session_id")) != record.session_id:
            return
        device_id = clean_text(identity.get("device_id"))
        board_profile = clean_text(identity.get("board_profile"))
        if not device_id or not board_profile:
            return
        record.endpoint_identity = dict(identity)
        record.status = "found" if record.status not in {"approved", "consumed"} else record.status
        record.error = None
        record.audit.append({"event": "endpoint_identity_received", "at": at, "supervisor_id": supervisor_id, "device_id": device_id})

    def _expire_old_sessions(self) -> None:
        for record in self._store.list():
            self._expire_record_if_needed(record)
            if record.status == "expired":
                self._store.upsert(record)

    def _expire_record_if_needed(self, record: HardwareBlePairingSessionRecord) -> None:
        if record.status in {"approved", "canceled", "consumed", "expired"}:
            return
        try:
            expires = datetime.fromisoformat(record.expires_at.replace("Z", "+00:00"))
        except Exception:
            return
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            record.status = "expired"
            record.updated_at = utcnow_iso()
            record.audit.append({"event": "expired", "at": record.updated_at})


@dataclass
class HardwareAccessRecord:
    request_id: str
    node_id: str
    resource_type: str
    operation: str
    supervisor_id: str | None
    adapter: str | None
    status: str
    policy: str
    reason: str | None
    created_at: str
    updated_at: str
    decided_at: str | None = None
    decided_by: str | None = None
    decision_reason: str | None = None
    lease_id: str | None = None
    expires_at: str | None = None
    revoked_at: str | None = None
    released_at: str | None = None
    broker_url: str | None = None
    token_hash: str | None = None
    provisioning: dict[str, Any] | None = None
    audit: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": HARDWARE_ACCESS_SCHEMA_VERSION,
            "request_id": self.request_id,
            "node_id": self.node_id,
            "resource_type": self.resource_type,
            "operation": self.operation,
            "supervisor_id": self.supervisor_id,
            "adapter": self.adapter,
            "status": self.status,
            "policy": self.policy,
            "reason": self.reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "decision_reason": self.decision_reason,
            "lease_id": self.lease_id,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
            "released_at": self.released_at,
            "broker_url": self.broker_url,
            "provisioning": dict(self.provisioning) if isinstance(self.provisioning, dict) else None,
            "token_hash": self.token_hash,
            "audit": [dict(item) for item in self.audit],
        }

    def to_api_dict(self, *, include_token: str | None = None) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("token_hash", None)
        if include_token:
            payload["lease_token"] = include_token
        return payload


class HardwareAccessStore:
    def __init__(self, path: Path | None = None) -> None:
        configured = clean_text(os.getenv("HEXE_HARDWARE_ACCESS_DB"))
        self._path = path or (Path(configured) if configured else repo_root() / "data" / "hardware_access.json")
        self._records: dict[str, HardwareAccessRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        items = raw.get("items") if isinstance(raw, dict) and isinstance(raw.get("items"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            request_id = clean_text(item.get("request_id"))
            if not request_id:
                continue
            self._records[request_id] = HardwareAccessRecord(
                request_id=request_id,
                node_id=clean_text(item.get("node_id")),
                resource_type=clean_text(item.get("resource_type"), "bluetooth"),
                operation=clean_text(item.get("operation"), "ble.scan"),
                supervisor_id=clean_text(item.get("supervisor_id")) or None,
                adapter=clean_text(item.get("adapter")) or None,
                status=clean_text(item.get("status"), "pending"),
                policy=clean_text(item.get("policy"), "disabled"),
                reason=clean_text(item.get("reason")) or None,
                created_at=clean_text(item.get("created_at"), utcnow_iso()),
                updated_at=clean_text(item.get("updated_at"), utcnow_iso()),
                decided_at=clean_text(item.get("decided_at")) or None,
                decided_by=clean_text(item.get("decided_by")) or None,
                decision_reason=clean_text(item.get("decision_reason")) or None,
                lease_id=clean_text(item.get("lease_id")) or None,
                expires_at=clean_text(item.get("expires_at")) or None,
                revoked_at=clean_text(item.get("revoked_at")) or None,
                released_at=clean_text(item.get("released_at")) or None,
                broker_url=clean_text(item.get("broker_url")) or None,
                token_hash=clean_text(item.get("token_hash")) or None,
                provisioning=dict(item.get("provisioning")) if isinstance(item.get("provisioning"), dict) else None,
                audit=[dict(row) for row in item.get("audit", []) if isinstance(row, dict)]
                if isinstance(item.get("audit"), list)
                else [],
            )

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": HARDWARE_ACCESS_SCHEMA_VERSION,
            "items": [record.to_dict() for record in sorted(self._records.values(), key=lambda item: item.created_at)],
        }
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def upsert(self, record: HardwareAccessRecord) -> HardwareAccessRecord:
        self._records[record.request_id] = record
        self._save()
        return record

    def get(self, request_id: str) -> HardwareAccessRecord | None:
        return self._records.get(clean_text(request_id))

    def get_by_lease(self, lease_id: str) -> HardwareAccessRecord | None:
        lease_key = clean_text(lease_id)
        if not lease_key:
            return None
        return next((record for record in self._records.values() if record.lease_id == lease_key), None)

    def list(self, *, node_id: str | None = None, status: str | None = None) -> list[HardwareAccessRecord]:
        node_key = clean_text(node_id)
        status_key = clean_text(status).lower()
        records = sorted(self._records.values(), key=lambda item: item.created_at, reverse=True)
        if node_key:
            records = [record for record in records if record.node_id == node_key]
        if status_key:
            records = [record for record in records if record.status == status_key]
        return records


class HardwareAccessService:
    def __init__(self, store: HardwareAccessStore, supervisor_store: object | None) -> None:
        self._store = store
        self._supervisor_store = supervisor_store

    def request_access(self, body: HardwareAccessRequestBody) -> tuple[HardwareAccessRecord, str | None]:
        request_id = f"hwar_{secrets.token_urlsafe(12)}"
        now = utcnow_iso()
        supervisor = self._select_supervisor(body)
        policy = supervisor_bluetooth_policy(supervisor) if supervisor is not None else bluetooth_access_policy()
        status = "pending" if policy == "ask" else "denied"
        token: str | None = None
        record = HardwareAccessRecord(
            request_id=request_id,
            node_id=clean_text(body.node_id),
            resource_type=body.resource_type,
            operation=body.operation,
            supervisor_id=clean_text(getattr(supervisor, "supervisor_id", None)) or None,
            adapter=clean_text(body.adapter) or None,
            status=status,
            policy=policy,
            reason=clean_text(body.reason) or None,
            created_at=now,
            updated_at=now,
            broker_url=supervisor_broker_url(supervisor) if supervisor is not None else None,
            provisioning=body.provisioning.model_dump(mode="json") if body.provisioning is not None else None,
            audit=[{"event": "requested", "at": now, "policy": policy}],
        )
        if supervisor is None:
            record.status = "denied"
            record.decision_reason = "bluetooth_supervisor_unavailable"
            record.audit.append({"event": "denied", "at": now, "reason": record.decision_reason})
        elif policy == "disabled":
            record.status = "denied"
            record.decision_reason = "bluetooth_policy_disabled"
            record.audit.append({"event": "denied", "at": now, "reason": record.decision_reason})
        elif policy in {"allowed", "trusted_only"}:
            record, token = self._grant(record, duration_s=body.duration_s)
        self._store.upsert(record)
        return record, token

    def decide(self, request_id: str, body: HardwareAccessDecisionBody, *, actor_id: str) -> tuple[HardwareAccessRecord, str | None]:
        record = self._store.get(request_id)
        if record is None:
            raise KeyError("hardware_access_request_not_found")
        if record.status != "pending":
            raise ValueError("hardware_access_request_not_pending")
        now = utcnow_iso()
        record.decided_at = now
        record.decided_by = clean_text(actor_id, "admin")
        record.decision_reason = clean_text(body.reason) or None
        record.updated_at = now
        if body.decision == "deny":
            record.status = "denied"
            record.audit.append({"event": "denied", "at": now, "actor_id": record.decided_by, "reason": record.decision_reason})
            self._store.upsert(record)
            return record, None
        supervisor = self._resolve_supervisor(record.supervisor_id)
        if supervisor is None:
            record.status = "denied"
            record.decision_reason = "bluetooth_supervisor_unavailable"
            record.audit.append({"event": "denied", "at": now, "actor_id": record.decided_by, "reason": record.decision_reason})
            self._store.upsert(record)
            return record, None
        record, token = self._grant(record, duration_s=body.duration_s)
        record.audit.append({"event": "approved", "at": now, "actor_id": record.decided_by})
        self._store.upsert(record)
        return record, token

    def release(self, lease_id: str, *, node_id: str) -> HardwareAccessRecord:
        node_key = clean_text(node_id)
        lease_key = clean_text(lease_id)
        for record in self._store.list(node_id=node_key):
            if record.lease_id == lease_key and record.status == "granted":
                now = utcnow_iso()
                record.status = "released"
                record.released_at = now
                record.updated_at = now
                record.audit.append({"event": "released", "at": now, "node_id": node_key})
                self._store.upsert(record)
                return record
        raise KeyError("hardware_access_lease_not_found")

    def list_for_node(self, node_id: str) -> list[HardwareAccessRecord]:
        self._expire_old_leases()
        return self._store.list(node_id=clean_text(node_id))

    def list_requests(self, *, status: str | None = None) -> list[HardwareAccessRecord]:
        self._expire_old_leases()
        return self._store.list(status=status)

    def validate_lease(self, body: HardwareLeaseValidationBody) -> dict[str, Any]:
        secret = hardware_lease_secret()
        if not secret:
            return {"ok": False, "valid": False, "error": "hardware_lease_secret_unconfigured"}
        try:
            _header, payload = verify_hs256(body.lease_token, [{"kid": "hardware-v1", "secret": secret}])
            claims = validate_claims(
                payload,
                audience=HARDWARE_LEASE_AUDIENCE,
                required_scopes=[f"hardware.bluetooth.{body.operation}"],
            )
        except ServiceTokenError as exc:
            return {"ok": True, "valid": False, "error": str(exc)}
        lease_id = clean_text(payload.get("lease_id") or claims.jti)
        record = self._store.get_by_lease(lease_id)
        if record is None:
            return {"ok": True, "valid": False, "error": "hardware_access_lease_not_found"}
        self._expire_old_leases()
        if record.status != "granted":
            return {"ok": True, "valid": False, "error": f"hardware_access_lease_{record.status}"}
        if record.node_id != clean_text(body.node_id) or payload.get("node_id") != clean_text(body.node_id):
            return {"ok": True, "valid": False, "error": "hardware_access_node_mismatch"}
        if record.resource_type != body.resource_type or payload.get("resource_type") != body.resource_type:
            return {"ok": True, "valid": False, "error": "hardware_access_resource_mismatch"}
        if record.operation != body.operation or payload.get("operation") != body.operation:
            return {"ok": True, "valid": False, "error": "hardware_access_operation_mismatch"}
        if clean_text(body.supervisor_id) and record.supervisor_id != clean_text(body.supervisor_id):
            return {"ok": True, "valid": False, "error": "hardware_access_supervisor_mismatch"}
        requested_adapter = clean_text(getattr(body, "adapter", None))
        token_adapter = clean_text(payload.get("adapter"))
        if requested_adapter and token_adapter and requested_adapter != token_adapter:
            return {"ok": True, "valid": False, "error": "hardware_access_adapter_mismatch"}
        record_provisioning = record.provisioning if isinstance(record.provisioning, dict) else None
        token_provisioning = payload.get("provisioning") if isinstance(payload.get("provisioning"), dict) else None
        body_provisioning = body.provisioning.model_dump(mode="json") if body.provisioning is not None else None
        if record.operation == "ble.provision_wifi":
            if not record_provisioning or not token_provisioning or not body_provisioning:
                return {"ok": True, "valid": False, "error": "hardware_access_provisioning_context_required"}
            for key in (
                "contract_version",
                "schema_version",
                "onboarding_session_id",
                "target_node_id",
                "node_profile_id",
                "payload_schema_id",
                "endpoint_ephemeral_public_key",
                "sequence",
            ):
                if clean_text(record_provisioning.get(key)) != clean_text(body_provisioning.get(key)):
                    return {"ok": True, "valid": False, "error": f"hardware_access_provisioning_{key}_mismatch"}
                if clean_text(token_provisioning.get(key)) != clean_text(body_provisioning.get(key)):
                    return {"ok": True, "valid": False, "error": f"hardware_access_provisioning_{key}_mismatch"}
            if clean_text(record_provisioning.get("expires_at")) and clean_text(record_provisioning.get("expires_at")) != clean_text(
                body_provisioning.get("expires_at")
            ):
                return {"ok": True, "valid": False, "error": "hardware_access_provisioning_expires_at_mismatch"}
            if clean_text(token_provisioning.get("expires_at")) and clean_text(token_provisioning.get("expires_at")) != clean_text(
                body_provisioning.get("expires_at")
            ):
                return {"ok": True, "valid": False, "error": "hardware_access_provisioning_expires_at_mismatch"}
            if clean_text(record_provisioning.get("pairing_nonce")) and clean_text(record_provisioning.get("pairing_nonce")) != clean_text(
                body_provisioning.get("pairing_nonce")
            ):
                return {"ok": True, "valid": False, "error": "hardware_access_provisioning_pairing_nonce_mismatch"}
            if clean_text(record_provisioning.get("claim_code_ref")) and clean_text(record_provisioning.get("claim_code_ref")) != clean_text(
                body_provisioning.get("claim_code_ref")
            ):
                return {"ok": True, "valid": False, "error": "hardware_access_provisioning_claim_code_ref_mismatch"}
        return {
            "ok": True,
            "valid": True,
            "lease": record.to_api_dict(),
            "claims": claims.to_dict(),
        }

    def _select_supervisor(self, body: HardwareAccessRequestBody) -> object | None:
        candidates = active_bluetooth_supervisors(self._supervisor_store)
        supervisor_id = clean_text(body.supervisor_id)
        if supervisor_id:
            return next((record for record in candidates if clean_text(getattr(record, "supervisor_id", "")) == supervisor_id), None)
        return candidates[0] if candidates else None

    def _resolve_supervisor(self, supervisor_id: str | None) -> object | None:
        if not supervisor_id:
            return None
        if self._supervisor_store is None or not hasattr(self._supervisor_store, "get"):
            return None
        record = self._supervisor_store.get(supervisor_id)
        if record is None or not supervisor_has_bluetooth(record) or freshness_state(record) != "online":
            return None
        return record

    def _grant(self, record: HardwareAccessRecord, *, duration_s: int | None) -> tuple[HardwareAccessRecord, str]:
        secret = hardware_lease_secret()
        if not secret:
            record.status = "denied"
            record.decision_reason = "hardware_lease_secret_unconfigured"
            record.updated_at = utcnow_iso()
            record.audit.append({"event": "denied", "at": record.updated_at, "reason": record.decision_reason})
            return record, ""
        now_ts = utc_ts()
        ttl = duration_s or hardware_lease_ttl_s()
        exp_ts = now_ts + ttl
        lease_id = f"hwlease_{secrets.token_urlsafe(12)}"
        claims = {
            "sub": record.node_id,
            "aud": HARDWARE_LEASE_AUDIENCE,
            "scp": [f"hardware.bluetooth.{record.operation}"],
            "iat": now_ts,
            "exp": exp_ts,
            "jti": lease_id,
            "lease_id": lease_id,
            "node_id": record.node_id,
            "resource_type": record.resource_type,
            "operation": record.operation,
            "supervisor_id": record.supervisor_id,
            "adapter": record.adapter,
        }
        if record.provisioning:
            claims["provisioning"] = dict(record.provisioning)
        token = sign_hs256({"alg": "HS256", "typ": "JWT", "kid": "hardware-v1"}, claims, secret=secret)
        expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc).isoformat()
        record.status = "granted"
        record.lease_id = lease_id
        record.expires_at = expires_at
        record.updated_at = utcnow_iso()
        record.token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        record.audit.append({"event": "granted", "at": record.updated_at, "lease_id": lease_id, "expires_at": expires_at})
        return record, token

    def _expire_old_leases(self) -> None:
        now = datetime.now(timezone.utc)
        for record in self._store.list(status="granted"):
            if not record.expires_at:
                continue
            try:
                expires = datetime.fromisoformat(record.expires_at.replace("Z", "+00:00"))
            except Exception:
                continue
            if expires <= now:
                record.status = "expired"
                record.updated_at = utcnow_iso()
                record.audit.append({"event": "expired", "at": record.updated_at})
                self._store.upsert(record)
