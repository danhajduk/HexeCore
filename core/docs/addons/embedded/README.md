# Embedded Addon Docs

This folder contains documentation for embedded addons that run inside the Core-managed runtime.

## Code Boundary

Status: Implemented

- Core addon discovery and registry code lives under `backend/app/addons/`.
- Embedded addon UI and API integration is handled by Core backend and frontend surfaces.
- Embedded addons are the canonical addon path only for Core-local extensions.
- MQTT coordination for embedded addons stays within the Core-owned messaging boundary.

## See Also

- [../addons/README.md](../addons/README.md)
- [../addons/addon-platform.md](../addons/addon-platform.md)
- [../../core/frontend/frontend-and-ui.md](../../core/frontend/frontend-and-ui.md)
- [../../nodes/README.md](../../nodes/README.md)
- [../standalone-archive/README.md](../standalone-archive/README.md)
