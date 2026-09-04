# Embedded Addon Docs

This folder contains documentation for embedded addons that run inside the Core-managed runtime.

## Code Boundary

Status: Implemented

- Core addon discovery and registry code lives under `backend/app/addons/`.
- Embedded addon UI and API integration is handled by Core backend and frontend surfaces.
- Embedded addons are the canonical addon path only for Core-local extensions.
- MQTT coordination for embedded addons stays within the Core-owned messaging boundary.
- Core-local embedded addon UIs are framed through `/api/addons/<addon_id>`.
  Remote or standalone addon runtimes may still advertise proxy targets under
  `/addons/proxy/<addon_id>/`.
- The embedded MQTT admin UI exposes principal registration actions for addon
  bridges, including approve, provision, and revoke controls.

## See Also

- [../README.md](../README.md)
- [../addon-platform.md](../addon-platform.md)
- [../../core/frontend/frontend-and-ui.md](../../core/frontend/frontend-and-ui.md)
- [../../nodes/README.md](../../nodes/README.md)
- [../standalone-archive/README.md](../standalone-archive/README.md)
