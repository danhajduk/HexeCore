# Hexe Node Template

This folder is the starter template for creating a new modular Hexe node.

## What To Rename First

Rename these template values for your real node:

- repo folder name
- Python package `node_template`
- frontend package name
- service template filenames in `scripts/systemd/` to `<node-name>-backend.service.in` and `<node-name>-frontend.service.in`
- node display name in docs and UI

## Structure

- `src/node_template/`
  Modular backend package
- `frontend/`
  Modular React + Vite frontend
- `scripts/`
  Operational entrypoints and systemd templates
- `docs/`
  Starter node documentation
- `runtime/`
  Mutable runtime state and logs
- `tests/`
  Starter backend test layout

## Backend Start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m node_template.main
```

## Frontend Start

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 8080
```

## Notes

- This template is intentionally modular by default.
- The backend and frontend are minimal, but real.
- Replace placeholder provider logic and onboarding details with the node's real behavior.
