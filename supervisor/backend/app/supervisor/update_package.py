from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import stat
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACKAGE_SCHEMA_VERSION = "hexe.supervisor.update_package.v1"
PACKAGE_MANIFEST_NAME = "manifest.json"
PACKAGE_FILES_PREFIX = "files/"
DEFAULT_INCLUDE_ROOTS = ("backend", "scripts", "systemd", "shared", "addons")
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "data",
    "dist",
    "node_modules",
    "runtime",
    "temp",
    "var",
}
DEFAULT_EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".sqlite", ".sqlite3", ".db", ".log")
SENSITIVE_NAME_MARKERS = ("token", "password", "secret", "credential", "private_key", "authorization")
MAX_PACKAGE_BYTES = 64 * 1024 * 1024


class SupervisorUpdatePackageError(ValueError):
    pass


@dataclass(frozen=True)
class SupervisorUpdatePackage:
    package_id: str
    manifest: dict[str, Any]
    archive: bytes
    archive_sha256: str

    def to_request_payload(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "package_manifest": self.manifest,
            "package_archive_base64": base64.b64encode(self.archive).decode("ascii"),
            "package_archive_sha256": self.archive_sha256,
            "package_archive_size": len(self.archive),
        }


def _json_digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _safe_relative_path(value: object) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if not text or text.startswith("/") or "\x00" in text:
        raise SupervisorUpdatePackageError("package_path_invalid")
    parts = [part for part in text.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise SupervisorUpdatePackageError("package_path_escape")
    if text != "/".join(parts):
        raise SupervisorUpdatePackageError("package_path_invalid")
    return text


def _is_excluded(path: Path, rel: str) -> bool:
    parts = set(rel.split("/"))
    if parts.intersection(DEFAULT_EXCLUDED_DIRS):
        return True
    name = path.name.lower()
    if name.startswith(".env") or name.endswith(DEFAULT_EXCLUDED_SUFFIXES):
        return True
    if any(marker in name for marker in SENSITIVE_NAME_MARKERS):
        return True
    return False


def iter_supervisor_package_files(
    source_root: Path,
    *,
    include_roots: tuple[str, ...] = DEFAULT_INCLUDE_ROOTS,
) -> list[Path]:
    root = source_root.resolve()
    files: list[Path] = []
    for include in include_roots:
        include_rel = _safe_relative_path(include)
        include_path = root / include_rel
        if not include_path.exists():
            continue
        for path in sorted(include_path.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(root).as_posix()
            if _is_excluded(path, rel):
                continue
            files.append(path)
    return files


def build_supervisor_update_package(
    source_root: Path,
    *,
    source_version: str | None = None,
    commit_sha: str | None = None,
    compatibility: dict[str, Any] | None = None,
) -> SupervisorUpdatePackage:
    root = source_root.resolve()
    if not root.exists() or not root.is_dir():
        raise SupervisorUpdatePackageError("package_source_root_missing")
    entries: list[dict[str, Any]] = []
    file_bytes: dict[str, bytes] = {}
    for path in iter_supervisor_package_files(root):
        rel = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        mode = stat.S_IMODE(path.stat().st_mode)
        entries.append({"path": rel, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "mode": mode})
        file_bytes[rel] = raw
    if not entries:
        raise SupervisorUpdatePackageError("package_source_empty")
    manifest_base = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "source_version": source_version,
        "commit_sha": commit_sha,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "compatibility": dict(compatibility or {}),
        "files": entries,
    }
    manifest_digest = _json_digest(manifest_base)
    package_id = f"hexe-supervisor-{manifest_digest[:16]}"
    manifest = {**manifest_base, "manifest_digest": manifest_digest, "package_id": package_id}
    archive = _build_archive(manifest, file_bytes)
    return SupervisorUpdatePackage(
        package_id=package_id,
        manifest=manifest,
        archive=archive,
        archive_sha256=hashlib.sha256(archive).hexdigest(),
    )


def _build_archive(manifest: dict[str, Any], file_bytes: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    modes = {str(entry.get("path")): int(entry.get("mode") or 0o644) for entry in manifest.get("files", []) if isinstance(entry, dict)}
    with tarfile.open(fileobj=buffer, mode="w:gz", format=tarfile.PAX_FORMAT) as tf:
        manifest_raw = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8")
        info = tarfile.TarInfo(PACKAGE_MANIFEST_NAME)
        info.size = len(manifest_raw)
        info.mode = 0o644
        info.mtime = 0
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        tf.addfile(info, io.BytesIO(manifest_raw))
        for rel, raw in sorted(file_bytes.items()):
            safe_rel = _safe_relative_path(rel)
            file_info = tarfile.TarInfo(f"{PACKAGE_FILES_PREFIX}{safe_rel}")
            file_info.size = len(raw)
            file_info.mode = modes.get(safe_rel, 0o644) & 0o777
            file_info.mtime = 0
            file_info.uid = file_info.gid = 0
            file_info.uname = file_info.gname = ""
            tf.addfile(file_info, io.BytesIO(raw))
    return buffer.getvalue()


def decode_update_package_request(payload: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    manifest = payload.get("package_manifest")
    if not isinstance(manifest, dict):
        raise SupervisorUpdatePackageError("package_manifest_required")
    archive_b64 = str(payload.get("package_archive_base64") or "").strip()
    archive_sha256 = str(payload.get("package_archive_sha256") or "").strip().lower()
    if not archive_b64 or not archive_sha256:
        raise SupervisorUpdatePackageError("package_archive_required")
    try:
        archive = base64.b64decode(archive_b64.encode("ascii"), validate=True)
    except Exception as exc:
        raise SupervisorUpdatePackageError("package_archive_base64_invalid") from exc
    if len(archive) > MAX_PACKAGE_BYTES:
        raise SupervisorUpdatePackageError("package_archive_too_large")
    actual_sha = hashlib.sha256(archive).hexdigest()
    if actual_sha != archive_sha256:
        raise SupervisorUpdatePackageError("package_archive_checksum_mismatch")
    validate_update_package_archive(manifest, archive)
    return manifest, archive


def validate_update_package_archive(manifest: dict[str, Any], archive: bytes) -> None:
    validate_update_package_manifest(manifest)
    expected_files = {entry["path"]: entry for entry in manifest["files"]}
    seen_files: set[str] = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
            members = tf.getmembers()
            manifest_member = tf.extractfile(PACKAGE_MANIFEST_NAME)
            if manifest_member is None:
                raise SupervisorUpdatePackageError("package_archive_manifest_missing")
            archive_manifest = json.loads(manifest_member.read().decode("utf-8"))
            if archive_manifest != manifest:
                raise SupervisorUpdatePackageError("package_archive_manifest_mismatch")
            for member in members:
                if member.isdir():
                    continue
                if member.name == PACKAGE_MANIFEST_NAME:
                    continue
                if member.issym() or member.islnk() or not member.isfile():
                    raise SupervisorUpdatePackageError("package_archive_unsupported_member")
                if not member.name.startswith(PACKAGE_FILES_PREFIX):
                    raise SupervisorUpdatePackageError("package_archive_unexpected_member")
                rel = _safe_relative_path(member.name[len(PACKAGE_FILES_PREFIX) :])
                entry = expected_files.get(rel)
                if entry is None:
                    raise SupervisorUpdatePackageError("package_archive_unexpected_file")
                extracted = tf.extractfile(member)
                if extracted is None:
                    raise SupervisorUpdatePackageError("package_archive_file_unreadable")
                raw = extracted.read()
                if len(raw) != entry["size"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                    raise SupervisorUpdatePackageError("package_file_checksum_mismatch")
                seen_files.add(rel)
    except SupervisorUpdatePackageError:
        raise
    except Exception as exc:
        raise SupervisorUpdatePackageError("package_archive_invalid") from exc
    if seen_files != set(expected_files):
        raise SupervisorUpdatePackageError("package_archive_file_set_mismatch")


def validate_update_package_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != PACKAGE_SCHEMA_VERSION:
        raise SupervisorUpdatePackageError("package_schema_unsupported")
    package_id = str(manifest.get("package_id") or "").strip()
    if not package_id.startswith("hexe-supervisor-"):
        raise SupervisorUpdatePackageError("package_id_invalid")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise SupervisorUpdatePackageError("package_manifest_files_required")
    seen: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise SupervisorUpdatePackageError("package_manifest_file_invalid")
        rel = _safe_relative_path(item.get("path"))
        if rel in seen:
            raise SupervisorUpdatePackageError("package_manifest_duplicate_file")
        seen.add(rel)
        if not isinstance(item.get("size"), int) or item["size"] < 0:
            raise SupervisorUpdatePackageError("package_manifest_size_invalid")
        sha = str(item.get("sha256") or "").strip().lower()
        if len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha):
            raise SupervisorUpdatePackageError("package_manifest_sha256_invalid")
        mode = item.get("mode")
        if not isinstance(mode, int) or mode < 0 or mode > 0o777:
            raise SupervisorUpdatePackageError("package_manifest_mode_invalid")
    digest_payload = {key: value for key, value in manifest.items() if key not in {"manifest_digest", "package_id"}}
    if str(manifest.get("manifest_digest") or "") != _json_digest(digest_payload):
        raise SupervisorUpdatePackageError("package_manifest_digest_mismatch")
    if package_id != f"hexe-supervisor-{str(manifest['manifest_digest'])[:16]}":
        raise SupervisorUpdatePackageError("package_id_digest_mismatch")


def extract_update_package_archive(manifest: dict[str, Any], archive: bytes, destination: Path) -> list[Path]:
    validate_update_package_archive(manifest, archive)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    expected_files = {entry["path"]: entry for entry in manifest["files"]}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile() or not member.name.startswith(PACKAGE_FILES_PREFIX):
                continue
            rel = _safe_relative_path(member.name[len(PACKAGE_FILES_PREFIX) :])
            entry = expected_files[rel]
            target = (destination / rel).resolve()
            if not str(target).startswith(str(destination.resolve()) + os.sep):
                raise SupervisorUpdatePackageError("package_extract_path_escape")
            source = tf.extractfile(member)
            if source is None:
                raise SupervisorUpdatePackageError("package_archive_file_unreadable")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read())
            target.chmod(int(entry["mode"]) & 0o777)
            written.append(target)
    return written
