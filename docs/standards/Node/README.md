# Hexe Node Standard

Last Updated: 2026-04-04 US/Pacific

## Purpose

This document is the main entrypoint for the Hexe node standard.

It defines how a new Hexe node should be structured, how it should behave, and how the detailed node-standard files fit together.

The standard is modular by default. New nodes should be designed as modular systems with clearly separated responsibilities, even when their first implementation is still small.

## Rule Model

This standard uses three rule levels:

- **Mandatory**
  Rules every Hexe node must satisfy.
- **Recommended**
  Strong guidance that should normally be followed.
- **Optional**
  Acceptable patterns that may be used when helpful.

## What This Standard Governs

This standard governs:

- node lifecycle and trust model
- backend structure
- API structure
- frontend structure
- scripts and operations
- background tasks and internal scheduler behavior
- onboarding, trust, and readiness progression
- persistence, configuration, and security boundaries
- provider boundaries
- testing and documentation expectations

This standard does not attempt to standardize:

- provider-specific business rules
- node-specific domain logic
- exact internal file counts
- exact package depth
- exact UI composition details

## Core Direction

New Hexe nodes should be:

- modular
- operator-visible
- safe to restart
- explicit about trust and readiness
- explicit about provider boundaries
- explicit about recurring work ownership

The standard prioritizes:

- stable responsibilities
- stable contracts
- stable operational behavior
- modular growth paths

over:

- identical repository shape
- identical filenames
- one exact implementation pattern

## How To Use This Standard

Use this file in three ways:

1. As the entrypoint when designing a new node.
2. As the index for the detailed node-standard documents.
3. As the top-level compliance summary before doing a deeper review.

Recommended reading order for a new node:

1. [core-node-model.md](./core-node-model.md)
2. [backend-standard.md](./backend-standard.md)
3. [api-standard.md](./api-standard.md)
4. [frontend-standard.md](./frontend-standard.md)
5. [onboarding-trust-and-readiness-standard.md](./onboarding-trust-and-readiness-standard.md)
6. [scripts-and-operations-standard.md](./scripts-and-operations-standard.md)
7. [background-tasks-and-internal-scheduler-standard.md](./background-tasks-and-internal-scheduler-standard.md)
8. [persistence-configuration-and-security-standard.md](./persistence-configuration-and-security-standard.md)
9. [provider-boundary-standard.md](./provider-boundary-standard.md)
10. [testing-and-documentation-requirements.md](./testing-and-documentation-requirements.md)

## Standard Map

## 1. Core Node Model

[core-node-model.md](./core-node-model.md)

Defines the shared platform model for nodes:

- what a node is
- relationship to Core
- relationship to Supervisor
- lifecycle vocabulary
- trust model
- readiness model
- degraded-state model

## 2. Backend Standard

[backend-standard.md](./backend-standard.md)

Defines how the backend should be structured:

- modular backend domains
- runtime ownership
- onboarding and trust boundaries
- Core communication boundaries
- persistence and security boundaries

## 3. API Standard

[api-standard.md](./api-standard.md)

Defines the node API model:

- canonical route groups
- generic versus provider-specific routes
- request and response expectations
- error expectations
- compatibility rules

## 4. Frontend Standard

[frontend-standard.md](./frontend-standard.md)

Defines the node frontend model:

- setup and operational flows
- lifecycle and readiness visibility
- degraded-state visibility
- modular frontend structure expectations
- API access expectations

## 5. Onboarding, Trust, And Readiness Standard

[onboarding-trust-and-readiness-standard.md](./onboarding-trust-and-readiness-standard.md)

Defines how a node moves from local setup into trusted and operational behavior:

- onboarding session behavior
- approval visibility
- trust activation
- trusted resume
- post-trust blocked states
- readiness and degraded-state progression

## 6. Scripts And Operations Standard

[scripts-and-operations-standard.md](./scripts-and-operations-standard.md)

Defines the operational baseline for node repositories:

- required scripts
- environment-driven startup
- service installation
- restart and status control
- operator-facing operational predictability

## 7. Background Tasks And Internal Scheduler Standard

[background-tasks-and-internal-scheduler-standard.md](./background-tasks-and-internal-scheduler-standard.md)

Defines how recurring work should behave:

- scheduler ownership
- task state visibility
- startup and shutdown rules
- readiness interaction
- Core lease compatibility

## 8. Persistence, Configuration, And Security Standard

[persistence-configuration-and-security-standard.md](./persistence-configuration-and-security-standard.md)

Defines how nodes should manage local state safely:

- state categories
- validated configuration
- modular storage ownership
- API and logging safety
- runtime path boundaries

## 9. Provider Boundary Standard

[provider-boundary-standard.md](./provider-boundary-standard.md)

Defines the separation between node-generic and provider-specific behavior:

- provider setup boundaries
- provider API boundaries
- provider runtime boundaries
- provider readiness boundaries

## 10. Testing And Documentation Requirements

[testing-and-documentation-requirements.md](./testing-and-documentation-requirements.md)

Defines how a node proves and explains its behavior:

- required test categories
- minimum repo documentation
- repo-doc versus Core-doc ownership
- change-discipline expectations

## New Node Starter Structure

The following example tree shows a modular starting point for a new Hexe node.

This is not a mandatory exact layout, but it is the recommended default shape for new node creation.

```text
new-node/
├── README.md
├── requirements.txt
├── pyproject.toml
├── docs/
│   ├── architecture.md
│   ├── setup.md
│   ├── operations.md
│   └── provider-setup.md
├── scripts/
│   ├── bootstrap.sh
│   ├── run-from-env.sh
│   ├── stack-control.sh
│   ├── restart-stack.sh
│   ├── stack.env.example
│   └── systemd/
│       ├── <node-name>-backend.service.in
│       └── <node-name>-frontend.service.in
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── api/
│       │   └── client.js
│       ├── components/
│       │   └── status/
│       ├── features/
│       │   ├── onboarding/
│       │   ├── operational/
│       │   ├── providers/
│       │   └── diagnostics/
│       └── theme/
│           ├── tokens.css
│           └── components.css
├── src/
│   └── node_name/
│       ├── main.py
│       ├── config/
│       ├── runtime/
│       ├── onboarding/
│       ├── trust/
│       ├── core/
│       ├── capabilities/
│       ├── governance/
│       ├── providers/
│       ├── persistence/
│       ├── diagnostics/
│       └── security/
├── runtime/
│   ├── .gitkeep
│   └── logs/
└── tests/
    ├── test_config.py
    ├── test_onboarding.py
    ├── test_api.py
    ├── test_readiness.py
    ├── test_provider_boundary.py
    └── test_scheduler.py
```

Recommended interpretation of the starter structure:

- `src/node_name/main.py` owns startup wiring, not business logic
- `runtime/` under the package owns orchestration and long-lived runtime control
- `onboarding/`, `trust/`, `capabilities/`, and `governance/` remain distinct
- `providers/` holds provider-specific code only
- `persistence/` owns state stores and load/save boundaries
- `frontend/src/features/` separates setup, operational, provider, and diagnostics UI
- `runtime/` at the repo root stores mutable runtime data, not source code
- systemd template files should use node-specific names such as `<node-name>-backend.service.in` and `<node-name>-frontend.service.in`

## Main Rules Summary

At a high level, a Hexe node should:

- follow the canonical node lifecycle and trust model
- be modular by default
- keep backend, frontend, provider, and persistence boundaries clear
- keep onboarding distinct from provider setup
- expose readiness and degraded state clearly
- make recurring work explicit and observable
- validate configuration and protect sensitive data
- provide predictable scripts and operations
- include lifecycle-critical tests and operator-usable docs

## Compact Implementations

Compact implementations are allowed only as limited exceptions.

A compact area is acceptable only when:

- the node is still small
- ownership boundaries remain clear
- the structure can still grow modularly without rewriting contracts

A compact implementation is not acceptable when it causes:

- blurred lifecycle ownership
- mixed provider and node-generic logic
- hidden recurring work
- hidden sensitive-state handling
- unclear operator behavior

## Compliance Review Use

When reviewing a node against this standard, verify first that:

- lifecycle terms are used correctly
- trust and readiness are separated
- modular boundaries are visible
- provider behavior is contained
- recurring work is explicit
- runtime state is safe and restartable
- the operational baseline exists
- tests and docs cover lifecycle-critical behavior

Then use the detailed files for section-by-section review.
