from __future__ import annotations

import hashlib
import unittest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils

from app.store.models import ReleaseManifest
from app.store.signing import (
    VerificationError,
    run_pre_enable_verification,
    verify_detached_artifact_signature,
    verify_release_artifact,
    verify_rsa_signature,
)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_release_manifest(*, artifact_bytes: bytes, signature_b64: str = "", signature_type: str = "rsa-sha256") -> ReleaseManifest:
    return ReleaseManifest(
        id="hello_world",
        name="Hello World",
        version="1.2.3",
        core_min_version="0.1.0",
        core_max_version=None,
        dependencies=[],
        conflicts=[],
        checksum=_sha256_hex(artifact_bytes),
        publisher_id="pub-1",
        permissions=["filesystem.read"],
        signature={"publisher_id": "pub-1", "signature": signature_b64, "type": signature_type},
        compatibility={
            "core_min_version": "0.1.0",
            "core_max_version": None,
            "dependencies": [],
            "conflicts": [],
        },
    )


class TestStoreSigning(unittest.TestCase):
    def setUp(self) -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_key_pem = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    def _sign_digest(self, artifact_bytes: bytes) -> str:
        import base64

        digest = hashlib.sha256(artifact_bytes).digest()
        signature = self.private_key.sign(
            digest,
            padding.PKCS1v15(),
            utils.Prehashed(hashes.SHA256()),
        )
        return base64.b64encode(signature).decode("utf-8")

    def _sign_legacy_artifact(self, artifact_bytes: bytes) -> str:
        import base64

        signature = self.private_key.sign(artifact_bytes, padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(signature).decode("utf-8")

    def test_verify_release_artifact_success(self) -> None:
        artifact = b"addon-bundle-bytes"
        manifest = _build_release_manifest(artifact_bytes=artifact, signature_b64=self._sign_digest(artifact))
        verify_release_artifact(manifest, artifact, public_key_pem=self.public_key_pem)

    def test_verify_release_artifact_rejects_checksum_mismatch(self) -> None:
        artifact = b"good-bytes"
        manifest = _build_release_manifest(artifact_bytes=artifact, signature_b64=self._sign_digest(artifact))
        with self.assertRaises(VerificationError) as ctx:
            verify_release_artifact(manifest, b"tampered-bytes", public_key_pem=self.public_key_pem)
        self.assertEqual(ctx.exception.code, "checksum_mismatch")

    def test_signature_helpers_verify_digest_and_legacy_artifact_signatures(self) -> None:
        artifact = b"artifact"
        manifest = _build_release_manifest(artifact_bytes=artifact, signature_b64=self._sign_digest(artifact))
        verify_rsa_signature(manifest, public_key_pem=self.public_key_pem)
        verify_detached_artifact_signature(
            artifact_bytes=artifact,
            signature_b64=self._sign_legacy_artifact(artifact),
            public_key_pem=self.public_key_pem,
            signature_type="rsa-sha256",
        )

    def test_invalid_signature_rejected(self) -> None:
        artifact = b"artifact"
        manifest = _build_release_manifest(artifact_bytes=artifact, signature_b64=self._sign_digest(b"other"))
        with self.assertRaises(VerificationError) as ctx:
            verify_release_artifact(manifest, artifact, public_key_pem=self.public_key_pem)
        self.assertEqual(ctx.exception.code, "signature_invalid")

    def test_pre_enable_pipeline_allows_enable_after_verification(self) -> None:
        artifact = b"addon-bundle"
        manifest = _build_release_manifest(artifact_bytes=artifact, signature_b64=self._sign_digest(artifact))

        called = {"enabled": False}

        def enable_addon() -> str:
            called["enabled"] = True
            return "enabled"

        result = run_pre_enable_verification(
            manifest=manifest,
            artifact_bytes=artifact,
            public_key_pem=self.public_key_pem,
            enable_addon=enable_addon,
        )
        self.assertEqual(result, "enabled")
        self.assertTrue(called["enabled"])

    def test_pre_enable_pipeline_blocks_enable_when_verification_fails(self) -> None:
        artifact = b"addon-bundle"
        manifest = _build_release_manifest(artifact_bytes=artifact, signature_b64=self._sign_digest(b"other"))

        called = {"enabled": False}

        def enable_addon() -> str:
            called["enabled"] = True
            return "enabled"

        with self.assertRaises(VerificationError):
            run_pre_enable_verification(
                manifest=manifest,
                artifact_bytes=artifact,
                public_key_pem=self.public_key_pem,
                enable_addon=enable_addon,
            )
        self.assertFalse(called["enabled"])


if __name__ == "__main__":
    unittest.main()
