# Provider Boundary Standard

Last Updated: 2026-04-04 US/Pacific

## Purpose

This document defines the standard for separating node-generic behavior from provider-specific behavior in Hexe nodes.

The goal is to let nodes support provider-specific functionality without allowing provider logic to take over the node lifecycle, trust model, API model, or readiness model.

## Rule Levels

- **Mandatory**
  Every Hexe node must satisfy these rules when it supports provider-specific functionality.
- **Recommended**
  Strong guidance that should usually be followed.
- **Optional**
  Acceptable patterns that may be used when helpful.

## Core Principle

The provider boundary standard prioritizes:

- clear node-generic ownership
- explicit provider namespaces
- modular provider integration
- provider-specific extensibility without lifecycle drift

New nodes should treat provider support as a modular extension of the node, not as the structure that defines the node itself.

## 1. Node-Generic Versus Provider-Specific Responsibilities

### Mandatory

Node-generic responsibilities must remain distinct from provider-specific responsibilities.

### Mandatory

Node-generic responsibilities include:

- onboarding
- trust activation
- trusted identity
- lifecycle state
- capability lifecycle
- governance and readiness model
- service control
- generic node status

### Mandatory

Provider-specific responsibilities include:

- provider credentials or provider setup
- provider health checks
- provider-specific polling or recurring work
- provider-specific execution paths
- provider-specific storage
- provider-specific UI surfaces

### Mandatory

Provider-specific responsibilities must not redefine node-generic lifecycle semantics.

## 2. Modular Provider Structure

### Mandatory

New nodes should implement provider support modularly.

Provider-specific logic must not be scattered unpredictably through generic node runtime code.

### Recommended

Use a dedicated provider boundary such as:

- `providers/`
- provider adapter modules
- provider registry modules
- provider-specific stores
- provider-specific route groups

### Optional

Nodes may support one or many providers, but the provider boundary should be built as a reusable pattern even when only one provider exists initially.

## 3. Provider Setup Boundary

### Mandatory

Provider setup must be distinct from onboarding and trust establishment.

### Mandatory

A node must not treat:

- provider credential save
- provider OAuth
- provider connection checks

as equivalent to node trust activation.

### Recommended

Provider setup should appear as post-trust or post-basic-configuration work within the node’s setup model.

## 4. Provider API Boundary

### Mandatory

Provider-specific APIs must live under an explicit provider-oriented namespace.

### Mandatory

Provider APIs must not host generic node lifecycle actions such as:

- onboarding start
- onboarding status
- trust state
- generic readiness state

### Recommended

Use route structures such as:

- `/api/providers/{provider_id}/...`
- provider-specific namespaces only for clearly provider-owned actions

## 5. Provider State Boundary

### Mandatory

Provider state must be persisted separately enough from node-generic state that trust, lifecycle, and provider behavior do not overwrite each other conceptually.

### Mandatory

Provider credentials, provider caches, and provider checkpoints must not be stored as if they were node trust state.

### Recommended

Use provider-specific stores or namespaced state boundaries for:

- provider config
- provider credentials metadata
- provider caches
- provider task state
- provider runtime status

## 6. Provider Readiness Boundary

### Mandatory

Provider readiness is not the same as node trust.

### Mandatory

Provider readiness may affect operational readiness, but only through explicit readiness rules.

### Recommended

The node should distinguish:

- node trusted
- provider configured
- provider connected or healthy
- provider enabled for active use

### Mandatory

If provider readiness blocks operation, that relationship must be explicit in the node’s readiness model.

## 7. Provider Capability Boundary

### Mandatory

Provider capability reporting must fit into the node capability model rather than replacing it.

### Mandatory

Provider-specific features such as models, enabled providers, or provider access must be expressed through the node’s capability and readiness architecture where applicable.

### Recommended

Use the platform capability taxonomy concepts consistently, including:

- task families
- provider access
- provider models

## 8. Provider Runtime And Execution Boundary

### Mandatory

Provider-specific execution flows must sit under node runtime orchestration, not replace it.

### Mandatory

The node runtime remains the owner of:

- when execution is allowed
- whether trust and readiness prerequisites are satisfied
- whether governance and budget constraints are satisfied

### Recommended

Provider adapters should focus on provider-specific translation, health, and execution behavior rather than global lifecycle control.

## 9. Provider-Specific Background Work

### Mandatory

Provider-specific recurring work must still follow the node’s scheduler and background-task rules.

### Mandatory

Provider polling or provider refresh loops must not become invisible private behavior outside the node’s recurring-work model.

### Recommended

Provider-specific recurring work should report state through the same scheduler or task-visibility patterns used elsewhere in the node.

## 10. UI Boundary

### Mandatory

Provider-specific UI must not replace the generic node setup and operational model.

### Mandatory

The UI must preserve a distinction between:

- node onboarding and trust
- provider setup
- provider operational state

### Recommended

Provider setup should appear as one stage or domain within a larger setup model, not as the entire meaning of node readiness.

## 11. Security Boundary

### Mandatory

Provider credentials and provider runtime secrets must follow the same safety rules as trust-sensitive node state.

### Mandatory

Provider APIs, logs, and diagnostic payloads must not expose raw secrets in normal operation.

### Recommended

Use safe summaries and secret-present indicators for provider state visibility.

## 12. Multi-Provider Growth

### Mandatory

A new node should not be designed in a way that prevents future support for multiple providers if the node’s domain reasonably allows it.

### Recommended

Even when a node starts with a single provider, provider boundaries should be defined as a pattern rather than a one-off hardcoded special case.

## 13. Non-Compliance Signals

The node should be considered out of standard if:

- provider setup is treated as node onboarding
- provider APIs are used for generic node lifecycle actions
- provider state is mixed into generic trust state without a clear boundary
- provider runtime logic controls trust or lifecycle semantics directly
- provider polling exists with no scheduler or task visibility
- provider UI replaces the generic node setup model

## 14. Formal Compliance Checklist

Use this checklist during new-node design or standards review:

A node follows this standard when:

- node-generic and provider-specific responsibilities are clearly separated
- provider logic is modular
- provider setup is distinct from trust onboarding
- provider APIs are namespaced
- provider state is separated from trust state
- provider readiness is explicit
- provider capability reporting fits the node capability model
- provider-specific recurring work still follows node scheduler rules
