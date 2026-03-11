# Frontend and UI

## Frontend Architecture

Status: Implemented

- Stack: React + TypeScript + React Router + Vite.
- Entrypoints:
  - `frontend/src/main.tsx`
  - `frontend/src/App.tsx`
  - `frontend/src/core/router/routes.tsx`
- Shell layout wraps route output and admin session context.

## Route and Page Model

Status: Implemented

- Public route: `/`.
- Onboarding approval route: `/onboarding/nodes/approve?sid=...&state=...` (login-gated within page flow).
- Admin-gated routes: `/store`, `/addons`, `/settings`, `/settings/jobs`, `/settings/metrics`, `/settings/statistics`, and addon routes.
- Addon frame routes: `/addons/:addonId` and `/addons/:addonId/:section`.

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

- Home dashboard surfaces stack health, metrics, and activity.
- Settings organizes platform controls by subsystem.
- MQTT embedded UI includes overview/principals/users/runtime/audit/noisy-client pages.
- Node onboarding approval page requires normal admin session login before showing approval context.

## Planned

Status: Planned

- Formal feature-flag framework across frontend capabilities.
- Offline-first UI behavior.

## Archived Legacy Behavior

Status: Archived Legacy

- Split UI/theme docs (`frontend.md`, `theme.md`, `ui-theme.md`, `addon-ui-styling.md`) were consolidated into this canonical document.

## See Also

- [API Reference](./api-reference.md)
- [Addon Platform](./addon-platform.md)
- [MQTT Platform](./mqtt-platform.md)
- [Operators Guide](./operators-guide.md)
