# Core/Supervisor Mirror Drift Guard

Status: Implemented

`tools/check_mirror_drift.py` prevents accidental drift between the tracked Core and Supervisor source mirrors. The guard compares only tracked files so local caches, virtualenvs, build output, logs, and live runtime state do not affect the result.

Mirrored areas:

- `core/backend` to `supervisor/backend`
- `core/frontend` to `supervisor/frontend`
- `core/scripts` to `supervisor/scripts`
- `core/systemd` to `supervisor/systemd`
- `core/shared` to `supervisor/shared`
- `core/addons` to `supervisor/addons`

Documentation policy:

- `docs/` is the canonical repository documentation tree.
- `core/docs` and `supervisor/docs` must not contain tracked files.
- Local ignored files under `supervisor/docs` are archive/operator notes only; active task queues and current contracts belong under root `docs/`.

Intentional exceptions:

- Root `README.md` and `supervisor/README.md` describe different checkout entrypoints.
- Live runtime defaults under `core/var` and `supervisor/var` are outside this source mirror guard.

Run the guard from the repository root:

```bash
python tools/check_mirror_drift.py
```

`core/backend/tests/test_mirror_drift_guard.py` runs the same script as a repository-level regression check.
