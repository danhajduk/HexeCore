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
