# API Standard

Last Updated: 2026-04-04 US/Pacific

## Purpose

This document defines the API standard for Hexe nodes.

The goal is to produce node APIs that are:

- predictable for new node development
- stable for frontend integration
- compatible with Core proxying and lifecycle expectations
- clear about the boundary between generic node APIs and provider-specific APIs

## Rule Levels

- **Mandatory**
  Every Hexe node API must satisfy these rules.
- **Recommended**
  Strong guidance that should usually be followed.
- **Optional**
  Acceptable patterns that may be used when helpful.

## Core Principle

The API standard prioritizes:

- stable route groups
- typed request and response contracts
- consistent operator-facing semantics
- safe compatibility transitions

It does not require every node to expose the exact same full API surface.

It does require every node to organize its API around the same core categories.

## 1. API Design Model

### Mandatory

A node API must be organized into two kinds of surfaces:

- node-generic APIs
- node-specific or provider-specific APIs

Node-generic APIs are the standard surface expected across Hexe nodes.

Node-specific and provider-specific APIs are allowed only for functionality that does not belong in the generic node contract.

### Mandatory

Generic lifecycle, onboarding, trust, readiness, and service-control behavior must not be hidden inside provider-specific routes.

## 2. Transport And Payload Rules

### Mandatory

Node APIs must use JSON request and response payloads for normal application routes.

### Mandatory

Request and response shapes must be typed and validated at the backend boundary.

### Mandatory

Errors must return machine-readable JSON and must not rely on HTML error output for normal API behavior.

### Recommended

Use typed request and response models consistently across:

- generic node APIs
- provider APIs
- runtime action APIs

## 3. Canonical Route Groups

### Mandatory

Every node must organize APIs into these route groups when the functionality exists:

- health
- node status
- bootstrap or config
- onboarding
- capability configuration and declaration
- governance or readiness
- provider-specific routes
- service control routes
- runtime execution or runtime actions where applicable

### Recommended

These route groups should remain visibly separate in the codebase and in API documentation.

## 4. Health Routes

### Mandatory

Every node must expose health visibility sufficient for:

- process liveness
- general API health
- readiness or operational readiness visibility

### Recommended

Use clearly named routes such as:

- `/health/live`
- `/health/ready`
- `/api/health`

Equivalent patterns are allowed if their purpose remains clear.

## 5. Generic Node Routes

### Mandatory

Every node must provide a generic status route describing current node state.

This route must support operator visibility into the implemented lifecycle and readiness behavior.

### Recommended

Use a generic namespace rooted in `/api/node/` for node-wide concepts such as:

- status
- bootstrap
- config

### Optional

Compatibility aliases may exist outside `/api/node/` when needed during migration, but `/api/node/` should be treated as the preferred generic namespace for new nodes.

## 6. Onboarding Routes

### Mandatory

If a node performs onboarding, its local API must expose onboarding-related routes distinctly from provider setup routes.

These routes must support:

- onboarding start
- onboarding status visibility
- restart or reset behavior where allowed

### Mandatory

Local node onboarding routes must align semantically with the Core onboarding session contract even if the route shape differs locally.

### Recommended

Use clear route names under a generic onboarding namespace, such as:

- `/api/onboarding/start`
- `/api/onboarding/status`
- `/api/onboarding/restart`

## 7. Capability, Governance, And Readiness Routes

### Mandatory

Nodes that implement capability declaration and governance behavior must expose clear route groups for:

- capability configuration
- capability declaration
- governance status or refresh
- resolved readiness or blocker visibility

### Recommended

Use separate route groups rather than collapsing these concerns into one generic status response only.

### Mandatory

If a node can be blocked from becoming operational, the API must expose enough structured information for the frontend to present:

- readiness flags
- blocking reasons
- degraded causes where relevant

## 8. Provider-Specific Routes

### Mandatory

Provider-specific functionality must live under a provider-specific namespace.

Provider-specific routes must not redefine generic node lifecycle meanings.

### Recommended

Use namespaces shaped like:

- `/api/providers/{provider_id}/...`
- `/api/gmail/...`

as long as the provider boundary remains explicit and documented.

### Mandatory

Provider credential setup, provider health, provider polling, and provider-specific execution actions must remain clearly separate from generic onboarding and trust routes.

## 9. Service Control Routes

### Mandatory

If a node exposes runtime control or restart behavior, the API must expose it as explicit operational control, not as a side effect of unrelated endpoints.

### Recommended

Use a dedicated service control group such as:

- `/api/services/status`
- `/api/services/restart`

## 10. Runtime Action Routes

### Mandatory

Runtime execution, preview, or delegated execution routes are allowed only when they represent actual node functionality.

### Mandatory

These routes must be clearly separated from:

- setup routes
- onboarding routes
- provider configuration routes

### Recommended

Use route groups such as:

- `/api/runtime/...`
- `/api/tasks/...`

when the node provides runtime task features.

## 11. Request And Response Contract Rules

### Mandatory

API contracts must use stable field naming within a route family.

### Mandatory

Response payloads for operator-facing routes should expose readable state fields rather than only opaque status codes.

### Recommended

For major route groups, contracts should include:

- current status
- timestamps where meaningful
- blocking reasons where meaningful
- identifiers needed for follow-up actions

### Mandatory

Sensitive values such as trust tokens, provider secrets, service tokens, or raw credentials must not be exposed in normal API responses.

## 12. Error Contract Rules

### Mandatory

Failed requests must return JSON errors with enough structure for frontend handling.

At minimum, responses should support:

- a readable error message
- structured detail when needed
- appropriate HTTP status usage

### Recommended

Use consistent error shape patterns across the whole node API so the frontend does not need custom parsing per endpoint family.

### Mandatory

Error payloads must not leak secrets or unsafe internal details.

## 13. Compatibility And Migration Rules

### Mandatory

New node APIs should adopt the standard route grouping model from the start.

### Optional

Compatibility aliases may be kept when:

- an existing frontend depends on them
- Core proxying or migration paths depend on them
- the canonical route has already been defined and documented

### Recommended

When compatibility aliases exist, documentation should clearly mark:

- canonical route
- compatibility route
- expected migration direction

## 14. Core Proxy Compatibility

### Mandatory

Node APIs must be safe to proxy behind Core using a node-specific API base URL.

### Mandatory

Routes should avoid assumptions that the node API is always accessed directly on its local origin.

### Recommended

Use root-relative API handling in the frontend and stable route grouping in the backend to support both:

- direct node access
- Core-proxied access

## 15. Documentation Expectations

### Mandatory

Each node must document its API groups clearly enough that a new node frontend or operator flow can be built against them.

### Recommended

Important route groups should have at least one of:

- contract documentation
- OpenAPI visibility
- JSON schemas

## 16. Non-Compliance Signals

The API should be considered out of standard if:

- provider-specific routes are used for generic node lifecycle functions
- onboarding and provider setup are mixed into one route family
- error shapes are inconsistent across the node
- readiness blockers are only inferable from raw logs
- route grouping is too inconsistent for a generic frontend structure to integrate cleanly

## 17. Formal Compliance Checklist

Use this checklist during new-node design or standards review:

A node API is aligned with this standard when:

- it has clear generic route groups
- onboarding is distinct from provider setup
- capability/governance/readiness routes are explicit where implemented
- provider-specific APIs are clearly namespaced
- runtime actions are clearly separated from setup actions
- requests and responses are typed
- errors are JSON and consistent
- compatibility aliases, if any, are documented
