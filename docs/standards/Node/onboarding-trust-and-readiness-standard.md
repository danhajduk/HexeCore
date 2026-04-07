# Onboarding, Trust, And Readiness Standard

Last Updated: 2026-04-04 US/Pacific

## Purpose

This document defines the standard for onboarding, trust activation, post-trust setup, and readiness progression for Hexe nodes.

It describes how a new node should move from an untrusted local runtime into a trusted and operational platform participant.

## Rule Levels

- **Mandatory**
  Every Hexe node must satisfy these rules.
- **Recommended**
  Strong guidance that should usually be followed.
- **Optional**
  Acceptable patterns that may be used when helpful.

## Core Principle

The onboarding and readiness standard prioritizes:

- clear trust boundaries
- restart-safe behavior
- explicit operator visibility
- explicit blocked-state visibility
- clear separation between trust and capability readiness

## 1. Onboarding Model

### Mandatory

Every node that participates in Hexe Core onboarding must follow the generic node onboarding model.

This model includes:

- local node configuration
- onboarding session initiation
- operator approval visibility
- finalization handling
- trust activation persistence
- post-trust setup progression

### Mandatory

Provider setup must not replace or redefine onboarding.

Provider setup is post-trust or post-configuration work layered on top of node onboarding.

## 2. Canonical Lifecycle Alignment

### Mandatory

Nodes must align with the canonical node lifecycle vocabulary:

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

A node may project a simplified UI or local API state, but it must not redefine these lifecycle meanings incompatibly.

## 3. Pre-Trust Local State

### Mandatory

Before trust activation, the node must keep local configuration and pre-trust identity separate from trusted identity.

This includes:

- operator-provided Core endpoint information
- local node name or local node configuration
- temporary onboarding session context
- local bootstrap or discovery state

### Mandatory

Pre-trust state must not be treated as equivalent to Core-issued trust state.

## 4. Onboarding Session Start

### Mandatory

The node must be able to initiate onboarding through the Core onboarding session contract.

The node must send the fields required by Core for node onboarding, including:

- node name
- node type
- node software version
- protocol version
- node nonce
- hostname when applicable
- UI endpoint when applicable
- API base URL when applicable

### Recommended

Nodes should validate required onboarding inputs locally before attempting session creation.

## 5. Approval Visibility

### Mandatory

The node must surface approval visibility to the operator.

This includes:

- session ID when available
- approval URL when available
- current onboarding state
- terminal onboarding outcome when returned

### Mandatory

Nodes do not need embedded browser capability for onboarding.

The operator approval step may occur fully in Core, as long as the node can surface the approval URL and react correctly to finalization outcomes.

## 6. Finalization And Trust Activation

### Mandatory

The node must handle the finalize step explicitly.

Finalize behavior must support:

- waiting while approval is pending
- consuming approved trust activation payload
- handling terminal failure outcomes
- preventing unsafe reuse of stale or invalid finalize state

### Mandatory

Approved finalization is the only path to local trusted state.

### Mandatory

Trust activation material received from Core must be persisted safely and treated as protected data.

## 7. Trust Persistence And Resume

### Mandatory

A node must persist enough trusted state to resume safely after restart.

This includes, where applicable:

- trusted node identity
- trust token presence and metadata
- operational MQTT or equivalent trusted runtime metadata
- paired Core identity
- node-local post-trust state required for resume

### Mandatory

Trusted restart must not require the operator to repeat the onboarding flow when trust is still valid.

### Recommended

Startup should explicitly distinguish:

- no trust state present
- trust state present and resumable
- trust state present but invalid or outdated

## 8. Trust Loss And Terminal Trust States

### Mandatory

Nodes must support explicit Core-side trust loss handling.

This includes distinguishing:

- active trusted support
- trust revoked
- node removed

### Mandatory

When Core indicates revocation or removal, the node must stop treating itself as trusted until re-onboarded.

### Recommended

Nodes should expose trust-loss state clearly to operators instead of surfacing only generic auth or transport failures.

## 9. Post-Trust Setup Model

### Mandatory

Trust activation does not automatically make a node operational.

Trusted nodes must be allowed to remain in a blocked post-trust state while additional setup is completed.

### Mandatory

`capability_setup_pending` is the standard conceptual state for trusted-but-not-yet-operational nodes.

### Recommended

Post-trust setup may include:

- provider configuration
- capability selection
- capability declaration prerequisites
- governance prerequisites
- background-task readiness prerequisites

## 10. Capability Declaration And Governance Progression

### Mandatory

If the node participates in capability declaration, readiness progression must model these stages clearly:

- capability setup pending
- capability declaration in progress
- capability declaration accepted or failed
- governance sync or governance issuance
- operational readiness

### Mandatory

A node must not report itself as operational if trust exists but capability or governance prerequisites remain incomplete.

### Recommended

Operator-facing readiness should expose:

- capability state
- governance state
- operational readiness
- freshness or staleness signals where applicable

## 11. Readiness Model

### Mandatory

Readiness is a separate concern from trust.

### Mandatory

Nodes must be able to represent blocked readiness when any required condition remains incomplete.

Typical readiness conditions may include:

- trusted state present
- capability declaration accepted
- governance issued or current
- required provider readiness complete
- required background-task or runtime prerequisites complete

### Recommended

Readiness should be exposed with structured fields such as:

- readiness flags
- blocking reasons
- current stage
- last transition timestamps where meaningful

## 12. Degraded State Model

### Mandatory

Nodes must treat degraded operation as a first-class state.

Degraded state applies when the node still has enough runtime context to expose useful operator visibility, but cannot safely claim full operational readiness.

### Mandatory

Degraded state must be visible through local API and UI surfaces.

### Recommended

Common degraded causes should be distinguishable, such as:

- governance stale or outdated
- provider failures
- scheduler failures
- connectivity loss after trust
- invalid or partial runtime state

## 13. Operator Visibility Requirements

### Mandatory

Operators must be able to understand the node’s current setup and trust posture without reading logs.

At minimum, the node should expose:

- current lifecycle stage
- onboarding status
- trust state
- readiness state
- blocking reasons where applicable
- degraded state where applicable

### Recommended

The operator should be able to tell whether the node is:

- not configured
- waiting for approval
- trusted but still blocked
- operational
- degraded
- revoked or removed

## 14. Recovery Actions

### Mandatory

Nodes must define clear recovery behavior for non-terminal setup failures.

This includes, where implemented:

- restart setup
- retry finalize polling
- retry capability declaration
- retry governance refresh
- continue trusted resume on restart

### Mandatory

Recovery behavior must not silently discard valid trusted state unless the action explicitly intends to reset onboarding.

## 15. API And UI Requirements

### Mandatory

The node’s local API and UI must reflect the onboarding and readiness model consistently.

This includes:

- onboarding status visibility
- trust state visibility
- readiness visibility
- blocked-state visibility
- recovery action visibility

### Recommended

Nodes should avoid presenting onboarding, trust, capability, and governance as one undifferentiated status blob.

## 16. Non-Compliance Signals

The node should be considered out of standard if:

- provider setup is treated as onboarding
- trust is treated as locally self-issued
- trusted restart always forces a fresh onboarding flow
- readiness is conflated with trust
- blocked post-trust state is not visible
- trust loss from Core is not surfaced clearly

## 17. Formal Compliance Checklist

Use this checklist during new-node design or standards review:

A node follows this standard when:

- onboarding is explicit and Core-aligned
- approval visibility is operator-visible
- trust activation is explicit and safely persisted
- trusted resume works when trust remains valid
- trust loss is handled explicitly
- post-trust setup is modeled separately from trust
- readiness blockers are structured and visible
- degraded state is explicit
