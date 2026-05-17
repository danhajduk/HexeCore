# Testing And Documentation Requirements

Last Updated: 2026-04-04 US/Pacific

## Purpose

This document defines the minimum testing and documentation requirements for Hexe nodes.

The goal is to ensure that a new node is:

- verifiable
- operable
- understandable by future developers
- aligned with the shared Hexe node standard

## Rule Levels

- **Mandatory**
  Every Hexe node must satisfy these rules.
- **Recommended**
  Strong guidance that should usually be followed.
- **Optional**
  Acceptable patterns that may be used when helpful.

## Core Principle

These requirements prioritize:

- coverage of lifecycle-critical behavior
- coverage of operator-critical behavior
- documentation of boundaries and run paths
- separation of repo-specific docs from Core-wide contracts

Tests and documentation should reinforce the modular structure of the node rather than hide it.

## 1. Required Test Categories

### Mandatory

Every node must include tests for the behavior it actually implements across the following categories where applicable:

- configuration validation
- onboarding and trust flow
- backend API behavior
- capability, governance, and readiness behavior
- provider boundary behavior
- persistence behavior
- background-task or scheduler behavior
- service or runtime control behavior

### Recommended

Tests should reflect the modular structure of the node so responsibility boundaries remain visible in the test suite.

## 2. Configuration And Validation Tests

### Mandatory

If the node has typed configuration or environment loading, tests must verify:

- required values
- invalid values
- normalization of optional values
- important derived paths or runtime defaults where applicable

## 3. Onboarding And Trust Tests

### Mandatory

Nodes that implement onboarding must include tests for:

- onboarding initiation
- pending approval behavior
- finalization outcomes
- trust persistence
- trusted resume
- trust-loss or terminal trust handling where implemented

### Recommended

Tests should verify that trust is treated as Core-issued state rather than local assumption.

## 4. Backend API Tests

### Mandatory

Nodes must include API tests for their generic route groups where implemented.

This includes, as applicable:

- health routes
- node status routes
- onboarding routes
- capability routes
- governance or readiness routes
- service control routes
- provider-specific route groups

### Mandatory

API tests must cover both successful and important failure cases.

## 5. Capability, Governance, And Readiness Tests

### Mandatory

If the node implements post-trust readiness progression, tests must verify:

- capability setup blocked states
- readiness flags or blocking reasons
- governance-dependent readiness
- operational versus degraded transitions where implemented

## 6. Provider Boundary Tests

### Mandatory

If the node supports provider-specific behavior, tests must verify that provider logic stays within its boundary.

This includes, as applicable:

- provider setup
- provider API behavior
- provider stores
- provider health behavior
- provider-specific runtime behavior

### Recommended

Tests should help prevent provider behavior from accidentally taking over node-generic lifecycle logic.

## 7. Persistence Tests

### Mandatory

If the node persists runtime state, tests must verify:

- valid load behavior
- invalid or corrupt state handling
- safe save behavior
- restart-relevant state continuity

### Recommended

Persistence tests should align with the node’s modular storage boundaries.

## 8. Background-Task And Scheduler Tests

### Mandatory

If the node runs recurring work, tests must verify:

- scheduler startup behavior
- task state updates
- success and failure transitions
- readiness interaction where applicable
- safe handling of recurring task errors

### Recommended

If the node participates in Core-leased work, tests should verify lease-lifecycle compatibility behavior where implemented.

## 9. Frontend Tests

### Mandatory

If the node has a frontend with meaningful setup or operational behavior, it must include at least minimal frontend verification.

This should cover, as applicable:

- rendering of key setup states
- rendering of key operational states
- backend-unavailable behavior
- important status or blocker visibility

### Recommended

As the frontend becomes more modular, tests should follow feature boundaries rather than only one top-level render test.

## 10. Documentation Minimums

### Mandatory

Every node repository must include documentation for:

- repository purpose
- backend and frontend startup
- configuration entrypoints
- onboarding or setup flow
- operational controls
- architecture overview

### Recommended

The minimum repo docs should usually include:

- `README`
- architecture document
- setup or run guide
- operational guide or runbook
- provider setup guide where applicable

## 11. Repo Docs Versus Core Docs

### Mandatory

Repo documentation must cover repository-specific implementation and operation.

Core documentation must cover shared platform contracts and shared standards.

### Mandatory

A node repo must not silently diverge from Core-wide lifecycle, onboarding, API, or readiness standards.

### Recommended

Repo docs should link to the relevant Core standard or contract instead of duplicating canonical platform definitions unnecessarily.

## 12. Documentation Of Boundaries

### Mandatory

Node documentation must clearly describe:

- backend structure
- frontend structure
- provider boundary
- runtime and recurring-task behavior where applicable
- persistence and runtime-state locations

### Recommended

Boundary docs should use the same vocabulary as the Hexe node standard.

## 13. Documentation Of Operational Paths

### Mandatory

Node documentation must show operators and developers:

- how to configure the node
- how to start it
- how to restart it
- how to observe key state
- how to recover from common non-terminal setup or runtime issues

## 14. Change Discipline

### Recommended

When node architecture changes materially, documentation should be updated in the same work stream as the code change rather than deferred indefinitely.

### Recommended

Tests should be updated alongside architecture-affecting behavior changes so documentation and runtime behavior do not drift separately.

## 15. Non-Compliance Signals

The node should be considered out of standard if:

- onboarding or trust behavior exists without test coverage
- readiness-critical logic has no tests
- frontend setup or degraded behavior is undocumented and untested
- docs do not explain how to start or operate the node
- repo docs redefine shared platform contracts instead of linking to them
- documentation and code ownership boundaries are unclear

## 16. Formal Compliance Checklist

Use this checklist during new-node design or standards review:

A node follows this standard when:

- lifecycle-critical behavior is tested
- API behavior is tested
- persistence and configuration behavior are tested
- provider and scheduler behavior are tested where implemented
- frontend behavior has at least minimal verification where applicable
- the repo includes clear startup, setup, architecture, and operational docs
- repo docs align with Core-wide standards instead of conflicting with them
