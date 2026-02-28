# Addon Store Architecture (Phase 1)

Date: 2026-02-28
Status: Implemented foundation architecture

## Package Structure
- `backend/app/store/models.py`
  - Manifest and contract models (`AddonManifest`, `ReleaseManifest`, `CompatibilitySpec`, `SignatureBlock`)
  - Semver validation and explicit permission allowlist
  - `GET /api/store/schema` JSON schema export
- `backend/app/store/signing.py`
  - SHA256 checksum verification
  - RSA signature verification
  - Fail-closed structured verification errors
  - Pre-enable verification hook
- `backend/app/store/resolver.py`
  - Core version compatibility checks
  - Dependency presence validation
  - Conflict detection
  - Deterministic resolution ordering
- `backend/app/store/router.py`
  - Lifecycle endpoints for install/update/uninstall/status
  - Atomic unpack/swap/rollback flow
  - Safe archive extraction checks
  - SQLite audit store (`store_audit_log`)
- `backend/app/store/catalog.py`
  - Static JSON-backed catalog querying
  - Search, category filter, featured filter, sorting, pagination
- `backend/app/store/catalog.json`
  - Minimal static catalog seed data

## Trust Chain
1. Core receives release metadata + artifact bytes + publisher public key.
2. Core verifies checksum (`sha256`) against `ReleaseManifest.checksum`.
3. Core verifies RSA signature against canonicalized release payload.
4. Core validates compatibility constraints (core version, dependencies, conflicts).
5. Only after verification succeeds can install/update continue.
6. Addon enablement is blocked until verification stage succeeds.

## Install Lifecycle
1. Install/update request is authenticated (admin token).
2. Artifact is read from local package path.
3. Verification pipeline runs first (checksum + signature + compatibility resolver).
4. Package is extracted to staging with path traversal protection.
5. Install:
  - New addon path is atomically moved into `addons/<id>`.
6. Update:
  - Existing addon directory is atomically backed up.
  - New directory is atomically moved into place.
  - On failure, backup is restored.
7. Uninstall:
  - Addon directory is atomically moved to transient delete path then removed.
  - On failure, directory is restored.
8. Action result is recorded into `store_audit_log`.

## Dependency Resolution Model
- Resolver input:
  - `core_version`
  - requested addon manifest (`dependencies`, `conflicts`, min/max core versions)
  - installed addon set
- Enforcement:
  - Blocks if core version is below minimum or above maximum.
  - Blocks if required dependencies are missing.
  - Blocks if conflicts are already installed.
  - Blocks if the manifest internally overlaps dependency and conflict sets.
- Output:
  - Deterministic sorted dependency/conflict sets for predictable behavior.

## Future Billing Hook Points
- Add entitlement validation before lifecycle mutation in install/update endpoints.
- Extend audit records with entitlement/license decision fields.
- Add pricing and license metadata to catalog records.

## Future Sandbox Hook Points
- Validate requested addon permissions against policy before install/enable.
- Bind runtime sandbox profile from declared permissions.
- Block enablement if permission grant policy is not satisfied.

## Future Telemetry Hook Points
- Emit store lifecycle telemetry events (install attempts, failures, updates, uninstalls).
- Add catalog interaction telemetry (search/filter/install conversion).
- Correlate store audit entries with telemetry event IDs.

