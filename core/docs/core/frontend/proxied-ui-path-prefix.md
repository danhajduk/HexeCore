# Proxied UI Path-Prefix Requirements

Status: Implemented (contract definition)
Last updated: 2026-03-22

## Purpose

Defines the frontend path-prefix behavior required for any node UI or addon UI mounted below a Core-owned public path instead of the origin root.

This contract exists so proxied UIs continue working when mounted under:

- nodes: `/nodes/{node_id}/ui/`
- addons: `/addons/{addon_id}/`

## Canonical Public Bases

Node UI public base:

- `/nodes/{node_id}/ui/`

Addon UI public base:

- `/addons/{addon_id}/`

All frontend routing, asset resolution, redirects, and deep-link reload behavior must remain correct when those paths are the public mount root.

## Required Behavior

### Routing

- all frontend routing must work under a non-root base path
- internal navigation must preserve the mounted prefix
- browser refresh on a nested route must remain inside the mounted prefix
- deep links must load correctly when opened directly from the proxied public path

### Assets

- all static assets must resolve under the mounted public path
- asset URLs must not escape to `/` unless they are explicitly rewritten through the active proxy prefix
- relative asset URLs are preferred where practical

### Redirects And Links

- generated links must remain valid under the mounted public prefix
- redirects must preserve the mounted prefix
- frontend code must not navigate the browser to a root path that drops the prefix

## Rules

- UIs must not hardcode `/` as their routing base
- UIs must not hardcode absolute paths that escape the mounted prefix
- SPA routers must support a configurable basename or base
- server-rendered UIs must support a configurable root path or forwarded prefix
- any `<base href>` usage must match the mounted public prefix exactly

## Compatibility Patterns

### SPA UIs

- configure router basename or history base from runtime context
- configure asset base path from runtime context or the mounted page location
- use relative navigation targets when practical

### Server-Rendered UIs

- honor forwarded prefix or application root-path configuration
- generate relative links and redirects when practical
- ensure server-rendered asset URLs include the mounted prefix

## Required Acceptance Checks

A proxied UI is path-prefix compatible only if all of the following succeed:

- direct browser load of the UI entry path works
- direct browser load of a nested UI route works
- browser refresh on a deep-linked UI route works
- in-app navigation stays under the mounted prefix
- no broken asset URLs appear under the proxied path
- no redirect escapes the mounted prefix

## Failure Examples

Common path-prefix compatibility failures:

- assets loading from `/assets/...` instead of the mounted proxy path
- SPA router configured for `/` instead of `/nodes/{node_id}/ui/` or `/addons/{addon_id}/`
- login or post-action redirects dropping the mounted prefix
- browser refresh on a nested route returning a root-level 404 or the wrong app shell

## See Also

- [Proxied UI Contract](./proxied-ui-contract.md)
- [Frontend and UI](./frontend-and-ui.md)
- [Proxied UI Metadata](../api/proxied-ui-metadata.md)
