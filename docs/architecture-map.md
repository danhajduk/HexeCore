# Synthia Architecture Map

Last Updated: 2026-03-07 17:14 US/Pacific

## Topology

```text
Synthia Core
├── Backend (FastAPI)
│   ├── /api/* core endpoints
│   ├── Scheduler engine + queue/history stores
│   ├── Store/catalog/install lifecycle
│   ├── Auth/users/admin/session control plane
│   ├── Policy + telemetry + MQTT integration
│   └── Addon discovery/registry/proxy
├── Frontend (React + React Router)
│   ├── Core pages: Home, Store, Addons, Settings
│   ├── Admin session context + route gating
│   ├── Home operational dashboard polling + status cards
│   ├── Addons inventory/install wizard + admin uninstall flow
│   └── Dynamic addon route loading
├── Supervisor Integration
│   ├── Core writes desired.json + stages artifacts
│   ├── Supervisor reconciles desired -> runtime
│   └── Docker compose runs standalone services
└── Persistence
    ├── SQLite stores (settings/users/scheduler/history/stats/telemetry/store audit)
    └── JSON state files (registry/install sessions/policy/store metadata/runtime intent)
```

## Entrypoints

- Backend app: `backend/app/main.py`
- Supervisor app: `backend/synthia_supervisor/main.py`
- Frontend boot: `frontend/src/main.tsx`
- Frontend routes: `frontend/src/core/router/routes.tsx`

## Runtime Services

- systemd unit templates:
  - `systemd/user/synthia-backend.service.in`
  - `systemd/user/synthia-frontend-dev.service.in`
  - `systemd/user/synthia-supervisor.service.in`
  - `systemd/user/synthia-updater.service.in`

## Not Developed

- Distributed supervisor coordination
- Universal runtime policy enforcement for custom compose files
- Native supervisor metrics endpoint
