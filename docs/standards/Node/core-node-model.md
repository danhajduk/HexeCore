# Core Node Model

Last Updated: 2026-04-04 US/Pacific

## Purpose

This document defines the shared platform-level node model for Hexe.

It provides the common conceptual model that all node standards build on:

- what a node is
- how it relates to Core
- how it relates to Supervisor
- how lifecycle and trust work
- how readiness and degraded behavior should be understood

This document should be read as the conceptual anchor for all other node standard documents.

## Rule Levels

- **Mandatory**
  Every Hexe node must satisfy these rules.
- **Recommended**
  Strong guidance that should usually be followed.
- **Optional**
  Acceptable patterns that may be used when helpful.

## 1. What A Node Is

### Mandatory

A node is the canonical external execution and capability boundary in Hexe.

A node is not:

- an embedded addon
- the Core control plane
- the Supervisor runtime authority

### Mandatory

A node is a separately operating runtime that:

- establishes trust with Core
- exposes node-local APIs and UI as applicable
- declares capabilities to Core as applicable
- performs node-local runtime behavior
- may host provider-specific functionality behind node-generic lifecycle rules

## 2. Relationship To Core

### Mandatory

Core is the control plane for nodes.

Core remains responsible for:

- onboarding session authority
- approval decisions
- trust issuance
- governance issuance
- capability acceptance
- registry and proxy metadata

### Mandatory

Nodes must not redefine Core authority for trust, approval, or platform governance.

### Recommended

Nodes should treat Core as the source of truth for trust and governance decisions, while maintaining node-local visibility and cached state as needed for runtime continuity.

## 3. Relationship To Supervisor

### Mandatory

Supervisor is the host-local runtime authority when present.

Supervisor concerns include:

- process lifecycle control
- resource reporting
- host-local runtime coordination

### Mandatory

Nodes remain the canonical external functionality boundary even when Supervisor is present.

Supervisor does not replace the node model.

## 4. Canonical Node Lifecycle

### Mandatory

The canonical node lifecycle model is:

- `unconfigured`
- `bootstrap_connecting`
- `bootstrap_connected`
- `core_discovered`
- `registration_pending`
- `pending_approval`
- `trusted`
- `capability_setup_pending`
- `capability_declaration_in_progress`
- `capability_declaration_accepted`
- `capability_declaration_failed_retry_pending`
- `operational`
- `degraded`

### Mandatory

New node standards and node implementations must align with this lifecycle vocabulary even if local APIs or UIs project only part of it directly.

## 5. Lifecycle Meanings

### Mandatory

The canonical meanings are:

- `unconfigured`
  Local prerequisites are missing and the node cannot begin normal bootstrap.
- `bootstrap_connecting`
  The node is attempting to connect to bootstrap discovery or equivalent initial Core discovery flow.
- `bootstrap_connected`
  Bootstrap transport connectivity exists.
- `core_discovered`
  The node has enough Core bootstrap metadata to proceed with onboarding.
- `registration_pending`
  The node has initiated registration or onboarding session work but has not yet reached approved trust activation.
- `pending_approval`
  Core has a pending onboarding session awaiting operator decision.
- `trusted`
  Trust activation completed and the node has trusted credentials.
- `capability_setup_pending`
  The node is trusted but not yet ready for normal operation because post-trust setup remains incomplete.
- `capability_declaration_in_progress`
  The node is actively preparing or submitting capability declaration work.
- `capability_declaration_accepted`
  Capability declaration was accepted.
- `capability_declaration_failed_retry_pending`
  Capability declaration failed and the node is waiting to retry or be corrected.
- `operational`
  The node is ready for normal operation.
- `degraded`
  The node is impaired and must surface operator-visible warning or reduced-readiness behavior.

## 6. Canonical Lifecycle Sequence

### Recommended

The normal conceptual sequence is:

1. `unconfigured`
2. `bootstrap_connecting`
3. `bootstrap_connected`
4. `core_discovered`
5. `registration_pending`
6. `pending_approval`
7. `trusted`
8. `capability_setup_pending`
9. `capability_declaration_in_progress`
10. `capability_declaration_accepted`
11. `operational`

### Mandatory

Nodes may shortcut through already-satisfied stages on restart, but they must not violate the underlying lifecycle meaning.

## 7. Trust Model

### Mandatory

Trust is a Core-issued state, not a node-self-declared state.

### Mandatory

A node becomes trusted only after successful Core approval and trust activation.

### Mandatory

The node must persist enough trusted state to resume safely after restart when trust remains valid.

### Recommended

Nodes should expose trust state clearly through local API and UI surfaces so operators can distinguish:

- not yet trusted
- trusted and still configuring
- operational
- degraded

## 8. Capability Model

### Mandatory

Trust and capability are separate concepts.

Being trusted does not automatically make a node operational.

### Mandatory

If a node participates in capability declaration, it must treat capability activation as a post-trust stage.

### Recommended

The `capability_setup_pending` state should be used as the default conceptual model for the trusted-but-not-yet-operational stage.

## 9. Governance And Readiness Model

### Mandatory

Lifecycle state is not identical to readiness projection.

Nodes may expose or consume additional readiness-related state such as:

- capability status
- governance sync status
- operational readiness
- freshness or staleness projections

### Mandatory

A node should not present itself as fully operational if trust exists but capability, governance, or readiness requirements are still incomplete.

## 10. Degraded State Model

### Mandatory

`degraded` is a first-class node condition.

It is used when a node:

- was previously trusted or operational
- or has enough runtime context to function partially
- but is impaired in a way that should be visible to operators

### Mandatory

Degraded state must be surfaced through node-local APIs and UI when applicable.

### Recommended

Degraded behavior should preserve as much safe operator visibility as possible rather than collapsing into opaque failure.

## 11. Onboarding Session Model

### Mandatory

Nodes must align with the Core onboarding session model.

The canonical onboarding session outcomes are:

- `pending`
- `approved`
- `rejected`
- `expired`
- `consumed`
- `invalid`

### Mandatory

Nodes do not need embedded browser capability to complete onboarding.

The node only needs to surface the approval step for an operator and handle finalization outcomes correctly.

## 12. Node Identity Model

### Mandatory

Node identity has distinct stages:

- local pre-trust identity information
- onboarding session identity information
- trusted Core-issued node identity

### Mandatory

A node must not confuse operator-provided local configuration with trusted final identity.

## 13. Node-Generic Versus Provider-Specific Model

### Mandatory

Provider-specific setup and runtime behavior must be layered under the generic node model.

Provider behavior must not replace:

- onboarding
- trust
- lifecycle
- readiness semantics

## 14. Operational Visibility Model

### Mandatory

Every node must provide operator-visible understanding of:

- current lifecycle position
- trust state
- readiness blockers where applicable
- degraded causes where applicable

### Recommended

Operators should be able to determine whether a node is:

- not configured
- waiting for approval
- trusted but incomplete
- operational
- degraded

without reading internal logs.

## 15. Modular Growth Model

### Mandatory

New nodes should be designed to grow modularly from this shared node model.

### Recommended

Lifecycle, trust, onboarding, provider behavior, readiness, and runtime orchestration should be treated as separate conceptual modules even if some are implemented together at first.

## 16. Non-Compliance Signals

The node model should be considered out of standard if:

- trust is treated as node-self-issued
- provider setup replaces node onboarding
- lifecycle terms are redefined incompatibly
- readiness and operational state are conflated without explanation
- degraded behavior is not surfaced clearly

## 17. Formal Compliance Checklist

Use this checklist during new-node design or standards review:

A node follows the core node model when:

- it treats Core as the trust and governance authority
- it aligns with the canonical lifecycle vocabulary
- it separates trust from capability and readiness
- it preserves node-generic lifecycle semantics above provider-specific behavior
- it exposes operator-visible lifecycle and trust state
- it supports restart-safe trusted resume where applicable
