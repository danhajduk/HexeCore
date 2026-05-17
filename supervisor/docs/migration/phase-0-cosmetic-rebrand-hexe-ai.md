# Phase 0 Cosmetic Rebrand: Hexe AI

Status: Implemented
Last updated: 2026-03-20 10:25

## Purpose

Phase 0 establishes `Hexe AI` as the public-facing product identity for this repository without breaking the currently deployed runtime, node integrations, MQTT contracts, or API paths.

This phase is intentionally cosmetic and compatibility-first.

## Scope

Phase 0 changes only public-facing branding surfaces:

- UI branding
- public documentation
- OpenAPI and API metadata labels
- user-facing onboarding and notification text
- public platform identity configuration

## What Changes In Phase 0

Phase 0 introduces a public platform identity model with these defaults:

- `PLATFORM_NAME=Hexe AI`
- `PLATFORM_SHORT=Hexe`
- `PLATFORM_DOMAIN=hexe-ai.com`

Public-facing component names use these display labels:

- `Hexe AI`
- `Hexe Core`
- `Hexe Supervisor`
- `Hexe Nodes`

Frontend and backend user-facing text may use these public labels where the string is descriptive or display-oriented.

## What Does Not Change

Phase 0 does not rename internal identifiers or protocol literals.

The following remain unchanged in this phase:

- MQTT topic root: `synthia/...`
- API route paths such as `/api/system/...`
- internal package and module names
- service/unit filenames
- node contract field names
- protocol payload keys except where the field value itself is descriptive display text
- retained runtime identifiers such as `synthia-core`

## Compatibility Note

Phase 0 is a public-branding layer only.

Legacy internal naming remains active for compatibility:

- MQTT topics still use the `synthia` namespace
- API paths still use existing `/api/...` and `/api/system/...` route structure
- internal Python modules and packages still use `synthia` naming
- node trust, onboarding, governance, and budget contracts still keep their current keys and identifiers
- runtime/service identifiers such as `synthia-backend.service` remain unchanged

## Risks Avoided

By not renaming internals in Phase 0, this phase avoids:

- breaking MQTT consumers or topic ACLs
- breaking existing API clients
- breaking node onboarding and trust activation flows
- breaking stored state and runtime identifiers
- forcing cross-repository protocol migrations before the public brand is in place

## Future Phases

Later phases may evaluate deeper renames only after explicit compatibility planning.

Potential future work:

- optional public-domain rollout across deployed environments
- broader docs and asset refresh
- service/unit display-name cleanup where operationally safe
- long-horizon evaluation of internal identifier migration, if ever needed

Phase 0 should be treated as the compatibility-preserving foundation for those later decisions.
