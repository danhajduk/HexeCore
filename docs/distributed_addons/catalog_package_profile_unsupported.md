# Why `catalog_package_profile_unsupported` Happens

This error means the store install flow detected a package profile that Core does not install as an embedded addon.

For the current store pipeline, `POST /api/store/install` supports `embedded_addon` artifacts only.

## Error Breakdown

Common fields in this failure:

- `error=catalog_package_profile_unsupported`: Catalog install resolved an unsupported package profile.
- `package_profile=standalone_service`: Manifest/layout indicates a standalone service artifact.
- `supported_profiles=["embedded_addon"]`: Core installer accepts embedded-addon package layout only.
- `layout_hint=service_layout_app_main`: Installer found service-style layout (`app/main.py`).
- `catalog_release_package_profile=embedded_addon`: Catalog release metadata used during resolution.

## Why This Can Look Confusing

In this incident class, operators often see both of these at once:

1. Layout indicates a standalone service package.
2. Catalog release metadata claims embedded addon.

That combination can happen when:

- artifact packaging changed but catalog metadata was not updated, or
- catalog metadata is set to embedded addon for a service-layout artifact.

## Root Cause Summary

The artifact structure and catalog release profile are inconsistent with the embedded-addon install path.

Core blocks install to avoid deploying an artifact under the wrong execution model.

## Suggested Fixes

### Operator-Side (Immediate Triage)

1. Capture `catalog_addon_id`, `catalog_release_version`, and `artifact_url` from the failure payload.
2. Inspect artifact layout before retrying:
   - if it contains `app/main.py` and no `backend/addon.py`, treat it as `standalone_service`.
3. Choose one path and avoid mixed retries:
   - embedded path: wait for corrected embedded artifact + catalog metadata.
   - standalone path: deploy service externally and register in Core.

### Catalog-Maintainer (Permanent Remediation)

1. Keep artifact layout and `package_profile` aligned in the release metadata:
   - embedded addon artifact -> `package_profile=embedded_addon`
   - service-layout artifact -> `package_profile=standalone_service`
2. Rebuild and publish artifact if current package layout is incorrect.
3. Update catalog release entry (`artifact_url`, profile, signature/checksum metadata) to match the published bytes.
4. Confirm install behavior on a clean Core instance:
   - embedded path succeeds through `/api/store/install`, or
   - standalone path is documented and validated through external deploy + registry flow.

## Implementation-Ready Follow-Up Tasks

### Backend

1. Add a dedicated catalog consistency error when release metadata says `embedded_addon` but extracted artifact layout is service-like (`app/main.py`).
2. Extend `/api/store/status/{addon_id}` `last_install_error` with a stable `remediation_path` field (`embedded_repackage` or `standalone_deploy_register`).
3. Add API regression tests covering mismatch classification and status persistence.

### Catalog

1. Add release-publish validation to reject `package_profile=embedded_addon` when artifact inspection shows only service layout.
2. Require pre-publish artifact layout check output in catalog PR/release checklist.
3. Add a rollback note to pin prior known-good release when profile/layout mismatch is detected post-publish.

### UI

1. Render profile mismatch guidance as operator action cards in Addon Store install error surfaces.
2. Display `catalog_release_package_profile` and `layout_hint` in an expandable diagnostic panel.
3. Add frontend tests for mismatch error rendering and action text.
