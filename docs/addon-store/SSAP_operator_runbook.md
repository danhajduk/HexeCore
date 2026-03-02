# SSAP Standalone Service Operator Runbook

This runbook covers lifecycle operations for SSAP standalone services managed by Core + Supervisor.

## Paths and Ownership

- Desired state file:
  - `SynthiaAddons/services/<addon_id>/desired.json`
  - Owned by Core/operator intent.
- Runtime state file:
  - `SynthiaAddons/services/<addon_id>/runtime.json`
  - Owned by Supervisor reconcile loop.
- Versioned artifacts:
  - `SynthiaAddons/services/<addon_id>/versions/<version>/addon.tgz`
  - Staged by Core from catalog installs.
- Active pointer:
  - `SynthiaAddons/services/<addon_id>/current` symlink
  - Switched by Supervisor only after successful `docker compose up`.

## Install

1. Trigger catalog install from Core (`/api/store/install`).
2. Core verifies artifact, then stages it into:
   - `services/<addon_id>/versions/<version>/addon.tgz`
3. Core writes/updates desired state (`desired.json`) via SSAP fields.
4. Supervisor loop sees desired running state, verifies staged artifact again, then reconciles runtime.

## Start

1. Set `desired_state` to `running` in `desired.json`.
2. Supervisor sequence:
   1. Verify checksum/signature.
   2. Extract artifact.
   3. Generate compose/env files with security defaults.
   4. Run `docker compose up`.
   5. Atomically switch `current` symlink to new version.
3. Supervisor writes `runtime.json` with `state=running`.

## Stop

1. Set `desired_state` to `stopped` in `desired.json`.
2. Supervisor runs `docker compose down` for current version.
3. Supervisor writes `runtime.json` with `state=stopped`.

## Upgrade

1. Stage new version artifact under `versions/<new_version>/addon.tgz`.
2. Update `desired.json` `pinned_version` to new version.
3. Supervisor performs normal running reconcile and switches `current` only after successful start.
4. `runtime.json` tracks `active_version` and previous-version metadata.

## Rollback

On activation failure, Supervisor does not switch `current` and writes failure metadata in `runtime.json`:

- `state: "error"`
- `previous_version`
- `rollback_available`
- `last_error`

Rollback operation:

1. Point desired state back to prior working version (`pinned_version=<previous_version>`).
2. Keep `desired_state=running`.
3. Let Supervisor reconcile and reactivate previous version.

## Runtime Security Defaults

Generated compose/env defaults enforce:

- `privileged: false`
- `security_opt: [no-new-privileges:true]`
- Dedicated network (`synthia_net` by default)
- Localhost-bound published ports (`127.0.0.1:<host>:<container>/<proto>`)
- Env-file injection for service token (`SYNTHIA_SERVICE_TOKEN`)

## Troubleshooting

- SHA mismatch:
  - Check staged artifact hash and catalog release `sha256`.
  - Re-stage artifact from trusted catalog source.
- Signature failure:
  - Verify publisher key id and detached signature value in catalog metadata.
  - Confirm `publishers.json` path and active key status.
- Compose startup failure:
  - Inspect Supervisor `runtime.json:last_error`.
  - Inspect `docker compose` logs for service build/start errors.
- Missing MQTT announce/health:
  - Verify service runtime is `running`.
  - Verify addon publishes retained announce/health topics and broker connectivity.
