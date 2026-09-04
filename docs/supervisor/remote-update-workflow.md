# Remote Supervisor Update Workflow

Remote Supervisor updates are Core-authorized but Supervisor-executed. Core can ask a host to update; it cannot run arbitrary commands on that host.

## Update Detection

Core stores reported Supervisor version, heartbeat freshness, and sanitized update status in the Supervisor fleet registry.

- `GET /api/system/supervisors` returns fleet freshness and any stored `metadata.update_status` and `metadata.version_audit`.
- `GET /api/system/supervisors/{supervisor_id}/update/status` refreshes update capability from an online Supervisor.
- Core runs an advisory scheduled Supervisor version audit on startup and every 10 minutes by default. The audit classifies visible Supervisors as `current`, `outdated`, `unknown`, `unreachable`, `unsupported`, or `update_running` without triggering updates.
- Core also records `metadata.local_source_gate` for the Core-host Supervisor package source. Remote auto-update decisions must treat any non-`current` local gate as blocked.
- Update status does not imply liveness. Freshness still comes from Supervisor registration and heartbeat timestamps.

Supervisor-local status is exposed at `GET /api/supervisor/update/status` and includes reported version, install root, source path, git checkout state, updater availability, package staging/backup availability, supported update modes, and current or last update state.

## Local Source Gate

Before Core treats its local Supervisor package source as the desired fleet
version, it checks the source tree resolved from
`HEXE_SUPERVISOR_PACKAGE_SOURCE_ROOT` or the local mirrored `supervisor` tree.
The gate runs bounded git commands for branch, `HEAD`, upstream, upstream
commit, ahead/behind counts, dirty/untracked package contents, and optional
fetch status. It does not pull, merge, checkout, or mutate package contents.

Gate states:

- `current`: clean, has upstream, zero ahead/behind, fetch succeeded when
  enabled, and mirror drift guard passed.
- `behind`: local source is behind upstream.
- `ahead`: local source has commits not in upstream.
- `diverged`: local source is both ahead and behind upstream.
- `dirty`: package-relevant working tree changes or untracked files are present.
- `not_git`: source root is missing or not inside a git checkout.
- `fetch_failed`: bounded fetch failed or timed out.
- `unknown`: upstream/counts are unavailable or mirror drift guard failed.

The gate stores only safe classification fields and exit codes. It does not
store remote URLs or raw git stderr. Remote update triggering remains blocked
unless the gate is `current`.

## Authorization

Only Core admin authentication may request fleet update status or start an update through Core.

- `X-Supervisor-Token` reporting credentials are not accepted for Core update commands.
- Core refuses update commands for stale, offline, missing, or historical Supervisor records.
- Core forwards only modes advertised by the target Supervisor in `supported_modes`.

## Git Mode

`git` mode delegates to the target Supervisor host.

1. Operator requests `source_mode=git` through Core or directly on the Supervisor.
2. Core verifies the Supervisor is online and advertises `git`.
3. Core forwards `POST /api/supervisor/update/start`.
4. Supervisor starts only `systemctl --user start hexe-updater.service`.
5. The updater service runs the bounded local `scripts/update.sh` path from the Supervisor install root.
6. Supervisor records current/last update state in `var/supervisor/update-state.json`.
7. Core observes update progress through status polling and later heartbeat/version reports.

Git mode requires a valid git checkout, `scripts/update.sh`, and loaded `hexe-updater.service` on the target host.

## Core-Host Package Mode

`core_host` mode is for Supervisors installed from copied source trees or hosts that should not pull from git.

1. Operator requests `source_mode=core_host` through Core.
2. Core verifies the Supervisor is online and advertises `core_host`.
3. Core builds a Supervisor source package from `HEXE_SUPERVISOR_PACKAGE_SOURCE_ROOT` or the local sibling `supervisor` tree.
4. The manifest includes source version, commit SHA when available, compatibility metadata, file list, per-file size/mode/SHA-256, manifest digest, and package id.
5. Core uploads the manifest and base64 archive to `POST /api/supervisor/update/start`.
6. Supervisor validates archive SHA-256, manifest digest, archive manifest equality, file list, file sizes, file checksums, and every relative path.
7. Supervisor stages files under `var/supervisor/packages/staging/{package_id}`.
8. Supervisor creates a backup tarball under `var/supervisor/backups`.
9. Supervisor applies package files only inside its configured install root.
10. If `service_update=true`, Supervisor installs backend requirements, renders known Supervisor user units, runs `systemctl --user daemon-reload`, and `try-restart`s Supervisor units.
11. Core polls status and waits for the next heartbeat to show the new reported version.

The package builder excludes runtime state and likely secret material such as `.venv`, `.git`, `var`, `data`, `runtime`, logs, databases, and filenames containing token/password/secret/credential/private key markers.

## Idempotency

All update starts require an `idempotency_key`.

- Repeating the same running key returns the current update attempt.
- Repeating a finished key returns the finished attempt.
- Re-uploading an already applied `core_host` package id or manifest digest returns an idempotent already-applied response.

## Failure And Rollback

Malformed requests, unsupported modes, missing API URLs, stale/offline hosts, invalid package manifests, checksum mismatches, path traversal, invalid JSON, and concurrent updates fail closed.

Package validation failures occur before files are applied. If files were applied and a later dependency install, unit reload, or restart step fails, Supervisor records `state=failed`, `rollback_required=true`, `backup_path`, and sanitized error text.

Rollback is manual in this task. The backup tarball contains the overwritten files needed to restore the previous Supervisor source state.

## Operator UI

Core Settings / Supervisor shows reported Supervisor version, supported update modes, last update state/time/error, and update action buttons only for online Supervisors with advertised modes. Each UI action requires confirmation naming the target Supervisor, host, and selected source mode.

## Verification

Recommended non-mutating checks before a live update:

```bash
PYTHONPATH=core/backend core/backend/.venv/bin/python -m pytest -q \
  core/backend/tests/test_supervisor_update_package.py \
  core/backend/tests/test_supervisor_update_api.py \
  core/backend/tests/test_supervisor_fleet_api.py

PYTHONPATH=supervisor/backend supervisor/backend/.venv/bin/python -m pytest -q \
  supervisor/backend/tests/test_supervisor_update_package.py \
  supervisor/backend/tests/test_supervisor_update_api.py \
  supervisor/backend/tests/test_supervisor_fleet_api.py

npm --prefix core/frontend run test -- settingsSupervisorUpdate.test.ts
npm --prefix core/frontend run build
python tools/update_openapi_snapshot.py --check
python tools/check_mirror_drift.py
```

Live update verification should be run only against a Supervisor whose running API already includes the update endpoints from Tasks 992-994, because older Supervisors cannot receive the package mode request.

The 2026-09-02 dry-run verification built a Core-host package from the local `supervisor` source tree with 369 files and a 565295 byte archive. Live remote mutation was intentionally not run in that pass because the remote Supervisor must first be running the new package receive/apply API.
