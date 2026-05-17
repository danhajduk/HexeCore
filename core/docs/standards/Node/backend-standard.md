# Backend Standard

Last Updated: 2026-04-04 US/Pacific

## Purpose

This document defines the backend standard for Hexe nodes.

The goal is to standardize backend responsibilities and contracts while making modular backend structure the default for any new node.

## Rule Levels

- **Mandatory**
  Every Hexe node backend must satisfy these rules.
- **Recommended**
  Strong guidance that should be followed unless the node has a clear reason not to.
- **Optional**
  Acceptable patterns that may be used when helpful.

## Core Principle

The backend standard focuses on:

- responsibility boundaries
- contract clarity
- runtime predictability
- operational safety

It does not require:

- identical package depth
- identical module names in every repository
- identical subpackage names in every repository

It does require:

- modular responsibility boundaries
- clear separation between node-generic and provider-specific behavior
- a structure that can grow without collapsing multiple concerns into one file

New nodes should use a modular backend structure by default.

## 1. Required Backend Domains

### Mandatory

Every node backend must have clearly implemented ownership for the following domains:

- backend entrypoint
- lifecycle state handling
- onboarding and registration
- trust and identity
- Core communication
- capability handling
- governance and readiness
- runtime orchestration
- provider integration boundary
- persistence and state storage
- diagnostics and logging
- security and secret-safe behavior

These domains do not need to be one-folder-per-domain, but they must be clearly identifiable in code and documentation.

### Recommended

The domains should be represented by dedicated modules or packages whenever the node is intended for continued growth.

### Optional

Compact service-oriented structure is allowed only when:

- the node is still small
- responsibilities remain clearly separated
- the compact layout does not blur onboarding, runtime, provider, and persistence ownership
- the layout can still be split cleanly later without rewriting contracts

## 2. Backend Entrypoint

### Mandatory

Each node must expose one clear backend entrypoint responsible for:

- configuration loading
- logger initialization
- dependency wiring
- app creation
- startup behavior
- shutdown behavior

The entrypoint must be obvious to operators and developers.

### Recommended

Use a standard `main` module or equivalent single startup file.

The entrypoint should avoid holding domain logic that belongs in runtime, provider, onboarding, or persistence layers.

## 3. Lifecycle And Runtime Ownership

### Mandatory

Each node must have one clearly defined runtime orchestration owner.

This may be:

- one runtime coordinator with supporting modular services
- one main node service that delegates to modular domain services
- a small set of cooperating runtime services

The orchestrator must own:

- startup sequencing
- background task startup
- trust-aware runtime transitions
- shutdown sequencing
- service health context

### Recommended

The orchestrator should not also absorb all provider-specific and persistence-specific logic if that blurs boundaries too far.

New nodes should use a modular backend layout, typically with clearly separated areas such as:

- `runtime`
- `core` or `core_api`
- `providers`
- `persistence` or state stores
- `config`
- `security`

### Allowed variants

Acceptable shapes include:

- a `runtime/` package with multiple runtime services
- a hybrid model with one top-level coordinator and specialized subservices
- a central `NodeService` pattern only when surrounding domain modules remain clearly separated

## 4. Onboarding, Trust, And Identity Boundary

### Mandatory

The backend must clearly separate generic node onboarding behavior from provider-specific setup.

The node backend must implement:

- onboarding session creation or initiation
- approval/finalize progress handling
- trust material persistence
- trusted identity persistence
- restart-safe trust resume

Provider credential setup must not replace node onboarding.

### Recommended

Onboarding and trust code should live in dedicated modules or clearly bounded service sections.

Identity state and trust material should not be hidden inside generic config blobs.

## 5. Core Communication Boundary

### Mandatory

Each node must have a clear Core communication boundary.

This boundary must cover:

- onboarding-related Core calls
- capability declaration calls
- governance and readiness-related calls
- other node-generic Core interactions

### Recommended

Use dedicated Core client modules or dedicated service wrappers rather than scattering raw HTTP calls throughout unrelated code.

### Optional

The boundary may be implemented as:

- a `core/` package
- a `core_api/` package
- a small set of typed client modules

## 6. Capability, Governance, And Readiness Boundary

### Mandatory

The backend must expose a clear ownership boundary for:

- capability configuration or capability resolution
- capability declaration submission
- persisted accepted capability state where applicable
- governance sync or governance visibility
- readiness evaluation
- degraded-state determination

These concerns may interact closely, but they must remain conceptually separate from raw provider logic.

### Recommended

Readiness should be treated as a first-class backend concern, not as an incidental status field.

Blocking reasons and degraded conditions should be computed in a way that can be surfaced consistently through the API and UI.

## 7. Provider Integration Boundary

### Mandatory

Provider-specific code must be isolated from node-generic runtime code.

Provider-specific code includes:

- adapters
- provider health logic
- provider-specific APIs
- provider-specific storage
- provider-specific scheduling or polling logic

Node-generic code includes:

- onboarding
- trust
- generic status
- generic lifecycle
- generic service controls

### Recommended

Use a `providers/` namespace or equivalent.

Provider-specific modules should not become the default home for node lifecycle behavior.

## 8. Persistence And State Storage

### Mandatory

The backend must persist state categories explicitly rather than burying them in unstructured runtime memory.

The minimum categories are:

- operator or bootstrap config
- trust material
- node identity
- capability-related state
- governance-related state where applicable
- provider-related state where applicable
- background-task state where applicable

### Recommended

Use typed load/save boundaries and validation on read.

Corrupt or invalid persisted state should fail safely and produce operator-visible diagnostics.

### Optional

Allowed storage shapes include:

- JSON file stores
- SQLite-backed stores
- mixed storage depending on the state category

## 9. Configuration Management

### Mandatory

Configuration must be validated at load time.

Required values must fail clearly if missing or invalid.

Optional values must be normalized consistently.

### Recommended

Use typed config models and explicit runtime directories.

Avoid open-ended environment access spread throughout the codebase.

## 10. Diagnostics, Logging, And Error Handling

### Mandatory

The backend must provide:

- structured logging or consistently parseable logging
- safe error handling
- no raw secret logging
- actionable operator-visible error information for lifecycle-critical failures

### Recommended

Keep lifecycle-critical diagnostics separate enough that onboarding, readiness, and scheduler failures can be understood without reading unrelated provider logs.

### Mandatory

Errors returned through APIs must be safe to expose and must not leak credentials or internal tokens.

## 11. Background Task Ownership

### Mandatory

If the node backend runs recurring or long-lived background tasks, ownership must be explicit.

The backend must make clear:

- who starts the task
- who stops the task
- who reports task state
- who records last success and last failure

### Recommended

Background tasks should not be started from arbitrary modules without a runtime owner.

Scheduler-like behavior should be documented even if implemented inside a broader service.

## 12. Security Boundary

### Mandatory

The backend must treat secrets, trust tokens, provider tokens, and service tokens as protected data.

This includes:

- masked logging
- controlled persistence
- safe API output
- no accidental debugging leaks in normal operation

### Recommended

Secret-aware helpers should exist for masking, redaction, or safe summaries.

## 13. Allowed Implementation Variants

### Preferred variant: Modular backend layout

This is the default target for new nodes.

Typical characteristics:

- multiple modules or packages by responsibility
- explicit runtime and Core client modules
- separate persistence and diagnostics boundaries
- provider code isolated under a dedicated namespace

### Limited exception: Compact backend layout

This is allowed only for small nodes or early bootstrap phases.

Typical characteristics:

- one central orchestration file
- supporting typed models and config files
- clear domain separation still visible in code

### Mandatory rule across all variants

- required domains must exist
- modular responsibility boundaries must be preserved
- operator-visible behavior must remain consistent

## 14. Non-Compliance Signals

The backend should be considered out of standard if:

- onboarding and provider setup are blended together without a clear boundary
- Core calls are scattered without a defined client/service boundary
- lifecycle ownership is unclear
- state persistence categories are implicit or undocumented
- secrets appear in logs or API payloads
- background tasks have no clear owner or reported status
- compact structure has grown to the point that domain ownership is blurred

## 15. Formal Compliance Checklist

Use this checklist during new-node design or standards review:

A node backend is aligned with this standard when:

- it has a clear backend entrypoint
- runtime ownership is explicit
- onboarding, trust, and identity are clearly implemented
- Core communication is clearly bounded
- capability/governance/readiness logic is clearly owned
- provider-specific logic is isolated
- persistence categories are explicit
- configuration is validated
- logging is safe
- background task ownership is explicit where applicable
