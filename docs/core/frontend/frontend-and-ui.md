# Frontend and UI

## Frontend Architecture

Status: Implemented

- Stack: React + TypeScript + React Router + Vite.
- Entrypoints:
  - `frontend/src/main.tsx`
  - `frontend/src/App.tsx`
  - `frontend/src/core/router/routes.tsx`
- Shell layout wraps route output and admin session context.
- Platform branding is loaded through `PlatformBrandingProvider` in `frontend/src/core/branding.tsx` and sourced from `GET /api/system/platform`.

## Production UI Hosting

Status: Implemented

- Production Core UI is served from the built `frontend/dist` artifact by the Core backend.
- The production static frontend router is mounted after API, node proxy, addon proxy, and websocket proxy routes so backend-owned paths keep precedence.
- React route refreshes fall back to `frontend/dist/index.html`; missing static assets and reserved backend paths return backend 404 responses instead of the SPA shell.
- The default production browser model is same-origin: Core UI, `/api/*`, node proxy routes, and addon proxy routes share the Core public origin.
- Vite remains a development workflow only. Development CORS origins are enabled only when `HEXE_ENABLE_DEV_CORS=1` or explicit `HEXE_CORS_ALLOW_ORIGINS` values are configured.
- Production install, update, backend reload, and reload-all scripts rebuild the frontend artifact before restarting Core services.

## Route and Page Model

Status: Implemented

- Public route: `/`.
- Onboarding approval route: `/onboarding/nodes/approve?sid=...&state=...` (login-gated within page flow).
- Admin-gated routes: `/store`, `/addons`, `/settings`, `/settings/jobs`, `/settings/metrics`, `/settings/statistics`, and addon routes.
- Node routes: `/nodes/:nodeId` for registry details, `/nodes/:nodeId/UI` for the Core-proxied node UI iframe when the node registration exposes `ui_enabled=true` and a canonical `ui_base_url`, and `/nodes/:nodeId/rendered-ui` for the Core-rendered manifest-backed node UI shell.
- Addon frame routes: `/addons/:addonId` and `/addons/:addonId/:section`.
- Canonical backend proxy paths:
  - nodes: `/nodes/{node_id}/ui/` and `/nodes/{node_id}/ui/{path}`
  - addons: `/addons/{addon_id}/` and `/addons/{addon_id}/{path}`
  - legacy `/ui/nodes/...` and `/ui/addons/...` paths redirect to the canonical forms
- Backend proxy transport is shared through `backend/app/reverse_proxy.py`, which centralizes path joining, safe header forwarding, `X-Forwarded-*` injection, and Hexe target identity headers for addon/node proxy routes.
- The same proxy layer also handles websocket passthrough on those canonical and legacy UI paths for browser-driven realtime channels.
- Root-relative HTML, JS, and CSS asset references are rewritten through the active proxy prefix so proxied UIs continue working under `/nodes/.../ui` and `/addons/...` style mounts.
- When a proxied node/addon UI is unavailable, Core now returns an operator-readable HTML error shell instead of a blank iframe, and proxy timeouts are configurable for both node and addon targets.
- Proxy access uses the same admin token or signed admin session cookie model as the rest of Core admin surfaces, including websocket upgrades for proxied UIs.
- Proxy UI entrypoints also consult target health before forwarding when health metadata is available, so obviously unhealthy node/addon UIs fail fast into the fallback shell.
- Addon and node proxy flows emit structured `synthia.proxy` logs for UI, API, and websocket surfaces, including target id, public prefix, latency, status, and failure outcome for operator debugging.
- Before forwarding proxied UIs, Core now runs shared compatibility validation over the target metadata and returns explicit unavailable reasons for disabled UIs, missing endpoints, invalid endpoints, or prefix-incompatible targets.
- Target resolution for proxied node/addon UI and API surfaces is now centralized through a shared resolver service so route handlers no longer duplicate lookup and metadata interpretation logic.
- The canonical author-facing runtime/frontend requirements for externally mounted UIs are documented in [Proxied UI Contract](./proxied-ui-contract.md).

## Addon UI Conventions

Status: Implemented

- Addon UIs are rendered through Core iframe/proxy boundaries.
- MQTT addon setup-gate behavior redirects to setup section until setup is complete.
- Addon frame resolves embed target/runtime fallback from backend status APIs.

## Theming and Styling

Status: Implemented

- Theme tokens and CSS layers are maintained in `frontend/src/theme/*`.
- Core can inject shared theme tokens/classes into same-origin addon iframe documents.
- Shared addon styling guidance from prior theme docs is now consolidated here.

## Admin and Operator UX Patterns

Status: Implemented

- Home dashboard surfaces stack health and metrics.
- Settings organizes platform controls by subsystem.
- MQTT embedded UI includes overview/principals/users/runtime/audit/noisy-client pages.
- Node onboarding approval page requires normal admin session login before showing approval context.
- Major visible component labels now consume the shared branding abstraction instead of inferring product names from internal identifiers.

### Home Status Tiles

Status: Implemented

- Location: Home dashboard status row (`frontend/src/core/pages/Home.tsx`, `frontend/src/core/pages/home.css`).
- Icon source: `lucide-react`.
- Tile set:
  - `Core` -> `Cpu`
  - `Supervisor` -> `ShieldCheck`
  - `MQTT` -> `Waypoints`
  - `Scheduler` -> `Clock3`
  - `Workers` -> `Cog`
  - `Addons` -> `Puzzle`
  - `Network` -> `Network`
  - `Internet` -> `Globe`
  - `AI Node` -> `BrainCircuit`
- Tile contract:
  - width `96px`
  - height `72px`
  - border radius `12px`
  - icon size `24px`
  - label font size `12px`, line-height `1`
  - icon/label gap `6px`
  - centered tile content
- Responsive behavior:
  - desktop: auto-fit fixed-width `96px` tiles
  - <=`920px`: 4 tiles per row
  - <=`520px`: 3 tiles per row
  - <=`360px`: 2 tiles per row
- Screenshot reference:
  - `docs/screenshots/home-status-tiles.md`

## Planned

Status: Planned

- Formal feature-flag framework across frontend capabilities.
- Offline-first UI behavior.

## Archived Legacy Behavior

Status: Archived Legacy

- Split UI/theme docs (`frontend.md`, `theme.md`, `ui-theme.md`, `addon-ui-styling.md`) were consolidated into this canonical document.

## See Also

- [API Reference](../api/api-reference.md)
- [Addon Platform](../addons/addon-platform.md)
- [MQTT Platform](../mqtt/mqtt-platform.md)
- [Operators Guide](../operators-guide.md)
