from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .models import AddonManifest, ReleaseManifest


@dataclass
class ResolverError(Exception):
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


@dataclass
class ResolutionResult:
    addon_id: str
    addon_version: str
    core_version: str
    ordered_dependencies: list[str]
    checked_conflicts: list[str]


def _split_pre(pre: str) -> list[int | str]:
    out: list[int | str] = []
    for tok in pre.split("."):
        if tok.isdigit():
            out.append(int(tok))
        else:
            out.append(tok)
    return out


def _semver_parts(version: str) -> tuple[int, int, int, list[int | str]]:
    core, _, _build = version.partition("+")
    base, sep, pre = core.partition("-")
    parts = base.split(".")
    if len(parts) != 3:
        raise ResolverError(
            code="semver_invalid",
            message="Semver parsing failed.",
            details={"version": version},
        )
    major, minor, patch = (int(parts[0]), int(parts[1]), int(parts[2]))
    prerelease = _split_pre(pre) if sep else []
    return (major, minor, patch, prerelease)


def _compare_semver(a: str, b: str) -> int:
    pa = _semver_parts(a)
    pb = _semver_parts(b)

    if pa[:3] < pb[:3]:
        return -1
    if pa[:3] > pb[:3]:
        return 1

    pra = pa[3]
    prb = pb[3]
    if not pra and not prb:
        return 0
    if not pra:
        return 1
    if not prb:
        return -1

    for i in range(max(len(pra), len(prb))):
        if i >= len(pra):
            return -1
        if i >= len(prb):
            return 1
        va = pra[i]
        vb = prb[i]
        if va == vb:
            continue
        if isinstance(va, int) and isinstance(vb, str):
            return -1
        if isinstance(va, str) and isinstance(vb, int):
            return 1
        if va < vb:
            return -1
        return 1
    return 0


def _to_manifest_fields(manifest: AddonManifest | ReleaseManifest) -> tuple[str, str, str, str | None, list[str], list[str]]:
    return (
        manifest.id,
        manifest.version,
        manifest.core_min_version,
        manifest.core_max_version,
        list(manifest.dependencies),
        list(manifest.conflicts),
    )


def _normalize_installed(installed_addons: Mapping[str, str] | Iterable[str]) -> dict[str, str | None]:
    if isinstance(installed_addons, Mapping):
        return {str(k): str(v) for k, v in installed_addons.items()}
    return {str(k): None for k in installed_addons}


def resolve_manifest_compatibility(
    manifest: AddonManifest | ReleaseManifest,
    *,
    core_version: str,
    installed_addons: Mapping[str, str] | Iterable[str],
) -> ResolutionResult:
    addon_id, addon_version, core_min, core_max, dependencies, conflicts = _to_manifest_fields(manifest)

    installed = _normalize_installed(installed_addons)
    dep_set = sorted(set(x.strip() for x in dependencies if x.strip()))
    conflict_set = sorted(set(x.strip() for x in conflicts if x.strip()))

    if _compare_semver(core_version, core_min) < 0:
        raise ResolverError(
            code="core_version_too_low",
            message="Core version is below addon minimum requirement.",
            details={"core_version": core_version, "required_min": core_min},
        )

    if core_max is not None and _compare_semver(core_version, core_max) > 0:
        raise ResolverError(
            code="core_version_too_high",
            message="Core version is above addon maximum supported version.",
            details={"core_version": core_version, "required_max": core_max},
        )

    missing = [dep for dep in dep_set if dep not in installed and dep != addon_id]
    if missing:
        raise ResolverError(
            code="dependency_missing",
            message="Required dependencies are not installed.",
            details={"missing_dependencies": missing, "required_dependencies": dep_set},
        )

    dep_conflict_overlap = sorted(set(dep_set).intersection(conflict_set))
    if dep_conflict_overlap:
        raise ResolverError(
            code="manifest_inconsistent",
            message="Manifest contains addons listed in both dependencies and conflicts.",
            details={"overlap": dep_conflict_overlap},
        )

    installed_conflicts = [conflict for conflict in conflict_set if conflict in installed and conflict != addon_id]
    if installed_conflicts:
        raise ResolverError(
            code="conflict_detected",
            message="Installed addons conflict with requested addon.",
            details={"conflicts": installed_conflicts},
        )

    return ResolutionResult(
        addon_id=addon_id,
        addon_version=addon_version,
        core_version=core_version,
        ordered_dependencies=dep_set,
        checked_conflicts=conflict_set,
    )
