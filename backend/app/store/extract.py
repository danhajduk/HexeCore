from __future__ import annotations

import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any


def safe_extract_zip(zip_path: Path, extract_dir: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise RuntimeError(f"unsafe_archive_path:{member.filename}")
            target = (extract_dir / member_path).resolve()
            if not str(target).startswith(str(extract_dir.resolve())):
                raise RuntimeError(f"unsafe_archive_target:{member.filename}")
        zf.extractall(extract_dir)


def safe_extract_tar(tar_path: Path, extract_dir: Path) -> None:
    with tarfile.open(tar_path) as tf:
        for member in tf.getmembers():
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise RuntimeError(f"unsafe_archive_path:{member.name}")
            target = (extract_dir / member_path).resolve()
            if not str(target).startswith(str(extract_dir.resolve())):
                raise RuntimeError(f"unsafe_archive_target:{member.name}")
        tf.extractall(extract_dir)


def extract_package(package_path: Path, extract_dir: Path) -> None:
    suffixes = [s.lower() for s in package_path.suffixes]
    if package_path.suffix.lower() == ".zip":
        safe_extract_zip(package_path, extract_dir)
        return
    if suffixes[-2:] in [[".tar", ".gz"], [".tar", ".bz2"], [".tar", ".xz"]] or package_path.suffix.lower() == ".tar":
        safe_extract_tar(package_path, extract_dir)
        return
    raise RuntimeError("unsupported_package_type")


def find_addon_dir(extract_dir: Path, addon_id: str) -> Path:
    candidate = extract_dir / addon_id
    if candidate.is_dir():
        return candidate
    return extract_dir


def validate_addon_layout(addon_dir: Path, addon_id: str) -> dict[str, Any]:
    manifest_path = addon_dir / "manifest.json"
    backend_entry = addon_dir / "backend" / "addon.py"
    if not manifest_path.exists():
        raise RuntimeError("missing_manifest_json")
    if not backend_entry.exists():
        raise RuntimeError("missing_backend_entrypoint")
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("invalid_manifest_json") from exc
    if str(manifest_data.get("id", "")).strip() != addon_id:
        raise RuntimeError("manifest_id_mismatch")
    return manifest_data
