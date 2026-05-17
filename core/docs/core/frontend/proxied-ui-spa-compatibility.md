# Proxied UI SPA Compatibility Requirements

Status: Implemented (contract definition)
Last updated: 2026-03-22

## Purpose

Defines explicit compatibility requirements for SPA-based proxied UIs such as React/Vite applications mounted behind Core.

## Required Capabilities

- support a configurable router basename or base path
- support a configurable asset base path
- support runtime API base injection
- support reload on nested routes
- avoid hardcoded root-relative asset references unless they are known to be rewritten safely by Core

## Recommended Patterns

- derive router basename from runtime config
- derive fetch/API base path from runtime config or current location
- derive websocket path from runtime config or current location
- avoid embedding direct hostnames in frontend bundles

## Rules

- SPA navigation must stay under `/nodes/{node_id}/ui/` or `/addons/{addon_id}/`
- browser API calls must stay under `/api/nodes/{node_id}/` or `/api/addons/{addon_id}/`
- browser websocket traffic must stay on the Core public origin
- SPA bundles must not assume the app is mounted at `/`

## Acceptance Checks

A proxied SPA satisfies the compatibility contract only if:

- the SPA loads and navigates under the mounted prefix
- browser refresh works on nested routes through Core
- the browser network panel shows only Core-origin requests

## Failure Examples

Common SPA compatibility failures:

- a React Router basename left at `/`
- Vite asset base left at `/`
- API clients created from a hardcoded `http://localhost:...`
- websocket code using a fixed development hostname in production bundles

## See Also

- [Proxied UI Contract](./proxied-ui-contract.md)
- [Proxied UI Path-Prefix Requirements](./proxied-ui-path-prefix.md)
- [Proxied UI API Base-Path Requirements](./proxied-ui-api-base-path.md)
- [Proxied UI Runtime Config Contract](./proxied-ui-runtime-config.md)
