# Frontend Documentation

Last Updated: 2026-03-07 14:51 US/Pacific

## Stack

- React + TypeScript
- React Router (`BrowserRouter`, route object model)
- Vite-based frontend build/dev workflow

## Entrypoints

- `frontend/src/main.tsx`: initializes theme and mounts app
- `frontend/src/App.tsx`: wraps app in `AdminSessionProvider`, applies route tree
- `frontend/src/core/router/routes.tsx`: route definitions and admin protection logic

## Route Structure

- Public:
  - `/` (Home)
- Admin-gated:
  - `/store`
  - `/addons`
  - `/settings`
  - `/settings/jobs`
  - `/settings/metrics`
  - `/settings/statistics`
  - dynamically loaded addon routes

## Core UI Areas

- Home: admin sign-in/sign-out
- Store: catalog browsing, install actions, diagnostics and remediation UX
- Addons: inventory and control-plane metadata/actions
- Settings: settings + jobs/metrics/statistics + admin controls

## API Communication

- centralized client helpers in `frontend/src/core/api/client.ts`
- consumes backend endpoints for admin session, system stats, store, addons, scheduler

## Addon UI Integration

- dynamic route loading via `loadAddons.ts`
- addon routes wrapped in same admin-guard logic as core protected routes

## Styling and Theme

- theme token system under `frontend/src/theme/*`
- runtime theme init via `theme.ts`
- core layout/page CSS under `frontend/src/core/*/*.css`

## Not Developed

- Explicit offline-first frontend behavior
- Strict client-side feature flags framework
