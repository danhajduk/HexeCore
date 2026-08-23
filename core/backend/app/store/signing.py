from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .models import ReleaseManifest


@dataclass
class VerificationError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
            },
        }
        if self.details:
            payload["error"]["details"] = self.details
        return payload


def verify_checksum(artifact_bytes: bytes, expected_checksum: str) -> None:
    expected = _normalize_sha256(expected_checksum)
    actual = hashlib.sha256(artifact_bytes).hexdigest()
    if not expected:
        raise VerificationError(
            code="checksum_missing",
            message="Artifact checksum is missing or invalid.",
            details={"actual_sha256": actual},
        )
    if actual != expected:
        raise VerificationError(
            code="checksum_mismatch",
            message="Artifact checksum does not match release metadata.",
            details={"expected_sha256": expected, "actual_sha256": actual},
        )


def verify_rsa_signature(manifest: ReleaseManifest, public_key_pem: str) -> None:
    signature_b64 = str(manifest.signature.signature or "").strip()
    digest_hex = _normalize_sha256(manifest.checksum)
    if not digest_hex:
        raise VerificationError(code="checksum_missing", message="Artifact checksum is missing or invalid.")
    digest_bytes = bytes.fromhex(digest_hex)
    signature = _decode_signature(signature_b64)
    public_key = _decode_rsa_public_key(public_key_pem)
    try:
        public_key.verify(
            signature,
            digest_bytes,
            padding.PKCS1v15(),
            utils.Prehashed(hashes.SHA256()),
        )
    except InvalidSignature as exc:
        raise VerificationError(code="signature_invalid", message="Artifact signature is invalid.") from exc


def verify_detached_artifact_signature(
    *,
    artifact_bytes: bytes,
    signature_b64: str,
    public_key_pem: str,
    signature_type: str,
) -> None:
    signature = _decode_signature(signature_b64)
    digest_bytes = hashlib.sha256(artifact_bytes).digest()
    sig_type = _normalize_signature_type(signature_type)

    if sig_type == "ed25519":
        try:
            public_key = _decode_ed25519_public_key(public_key_pem)
            public_key.verify(signature, digest_bytes)
            return
        except VerificationError:
            # Compatibility: older catalog rows sometimes carried RSA keys while
            # labeling signatures as ed25519.
            if len(signature) == 64:
                raise
        except InvalidSignature as exc:
            raise VerificationError(code="signature_invalid", message="Artifact signature is invalid.") from exc

    if sig_type in {"rsa-sha256", "rsa", "ed25519"}:
        public_key = _decode_rsa_public_key(public_key_pem)
        _verify_rsa_signature_compat(public_key, signature, artifact_bytes, digest_bytes)
        return

    raise VerificationError(
        code="signature_type_unsupported",
        message=f"Unsupported artifact signature type: {signature_type}",
        details={"signature_type": signature_type},
    )


def verify_release_artifact(
    manifest: ReleaseManifest,
    artifact_bytes: bytes,
    public_key_pem: str,
) -> None:
    verify_checksum(artifact_bytes, manifest.checksum)
    verify_detached_artifact_signature(
        artifact_bytes=artifact_bytes,
        signature_b64=manifest.signature.signature,
        public_key_pem=public_key_pem,
        signature_type=manifest.signature.type,
    )


def run_pre_enable_verification(
    manifest: ReleaseManifest,
    artifact_bytes: bytes,
    public_key_pem: str,
    enable_addon: Callable[[], Any],
) -> Any:
    """
    Store install pipeline hook.
    Verification runs first; addon enablement is only invoked on success.
    """
    verify_release_artifact(
        manifest=manifest,
        artifact_bytes=artifact_bytes,
        public_key_pem=public_key_pem,
    )
    return enable_addon()


def _normalize_sha256(value: str | None) -> str:
    text = str(value or "").strip().lower()
    for prefix in ("sha256:", "sha256=", "sha256-"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    if len(text) == 64 and all(ch in "0123456789abcdef" for ch in text):
        return text
    return ""


def _normalize_signature_type(value: str | None) -> str:
    return str(value or "rsa-sha256").strip().lower().replace("_", "-") or "rsa-sha256"


def _decode_signature(signature_b64: str) -> bytes:
    text = str(signature_b64 or "").strip()
    if not text:
        raise VerificationError(code="signature_missing", message="Artifact signature is missing.")
    try:
        return base64.b64decode(text, validate=True)
    except Exception as exc:
        raise VerificationError(code="signature_invalid", message="Artifact signature is not valid base64.") from exc


def _normalize_key_text(public_key: str) -> str:
    text = str(public_key or "").strip()
    if not text:
        return ""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    if "\\n" in text or "\\r" in text:
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    return text


def _decode_rsa_public_key(public_key_pem: str) -> rsa.RSAPublicKey:
    text = _normalize_key_text(public_key_pem)
    if not text:
        raise VerificationError(code="publisher_key_missing", message="Publisher public key is missing.")
    try:
        key = serialization.load_pem_public_key(text.encode("utf-8"))
        if isinstance(key, rsa.RSAPublicKey):
            return key
    except Exception:
        pass
    try:
        key = serialization.load_der_public_key(base64.b64decode(text, validate=True))
        if isinstance(key, rsa.RSAPublicKey):
            return key
    except Exception:
        pass
    raise VerificationError(code="publisher_key_invalid", message="Publisher RSA public key is invalid.")


def _decode_ed25519_public_key(public_key: str) -> Ed25519PublicKey:
    text = _normalize_key_text(public_key)
    if not text:
        raise VerificationError(code="publisher_key_missing", message="Publisher public key is missing.")
    try:
        key = serialization.load_pem_public_key(text.encode("utf-8"))
        if isinstance(key, Ed25519PublicKey):
            return key
    except Exception:
        pass
    try:
        key = serialization.load_der_public_key(base64.b64decode(text, validate=True))
        if isinstance(key, Ed25519PublicKey):
            return key
    except Exception:
        pass
    for decoder in (base64.b64decode, bytes.fromhex):
        try:
            raw = decoder(text)
            if len(raw) == 32:
                return Ed25519PublicKey.from_public_bytes(raw)
        except Exception:
            continue
    raise VerificationError(code="publisher_key_invalid", message="Publisher Ed25519 public key is invalid.")


def _verify_rsa_signature_compat(
    public_key: rsa.RSAPublicKey,
    signature: bytes,
    artifact_bytes: bytes,
    digest_bytes: bytes,
) -> None:
    for payload, algorithm in (
        (digest_bytes, utils.Prehashed(hashes.SHA256())),
        (artifact_bytes, hashes.SHA256()),
    ):
        try:
            public_key.verify(signature, payload, padding.PKCS1v15(), algorithm)
            return
        except InvalidSignature:
            continue
    raise VerificationError(code="signature_invalid", message="Artifact signature is invalid.")
