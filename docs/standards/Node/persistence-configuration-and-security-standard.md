# Persistence, Configuration, And Security Standard

Last Updated: 2026-04-04 US/Pacific

## Purpose

This document defines the standard for local state persistence, configuration loading, and security-sensitive handling in Hexe nodes.

The goal is to make new nodes:

- restart-safe
- observable
- configurable in a predictable way
- safe with trusted and provider-sensitive data

## Rule Levels

- **Mandatory**
  Every Hexe node must satisfy these rules.
- **Recommended**
  Strong guidance that should usually be followed.
- **Optional**
  Acceptable patterns that may be used when helpful.

## Core Principle

This standard prioritizes:

- explicit state categories
- validated configuration
- secret-safe persistence
- safe API and logging boundaries
- modular storage ownership

New nodes should use modular state ownership by default, even when multiple state domains share one runtime directory or database.

## 1. State Categories Must Be Explicit

### Mandatory

Nodes must treat persisted state as explicit categories, not as one unstructured catch-all blob.

### Mandatory

The node must identify and manage the following categories when they exist:

- operator or bootstrap configuration
- onboarding session state
- trust material
- trusted node identity
- capability-related state
- governance-related state
- provider-related state
- scheduler or recurring-task state
- diagnostics artifacts where applicable

### Recommended

Different state categories should be managed by clearly separated stores, modules, or typed persistence boundaries.

## 2. Trusted And Sensitive Data Boundaries

### Mandatory

The node must treat these as sensitive data:

- trust tokens
- MQTT credentials
- provider secrets and tokens
- service tokens
- credential references that reveal secret material

### Mandatory

Sensitive data must not be exposed through normal API responses, UI payloads, or logs.

### Recommended

Use summaries, masked values, or secret-present indicators rather than raw secret values in operator-facing surfaces.

## 3. Persistence Model

### Mandatory

Nodes must persist the minimum data required for:

- restart-safe onboarding behavior
- restart-safe trusted resume
- readiness continuity
- recurring-task visibility where applicable

### Mandatory

The exact storage mechanism may vary, but the persistence strategy must be deliberate and documented.

### Optional

Allowed storage mechanisms include:

- JSON files
- SQLite
- mixed storage by state category

## 4. Configuration Model

### Mandatory

Node configuration must be validated at load time.

Required fields must fail clearly when absent or invalid.

Optional fields must be normalized consistently.

### Recommended

Use typed configuration models and explicit path fields for runtime files and directories.

### Mandatory

Configuration loading must be predictable enough that a new operator or developer can determine:

- which environment variables matter
- which files are runtime state
- which files are generated
- which paths are configurable

## 5. Modular Storage Ownership

### Mandatory

New nodes should use modular persistence ownership.

Trust, provider state, scheduler state, and governance state should not all be written by unrelated code to the same generic file without clear ownership.

### Recommended

Use one store or persistence boundary per meaningful state domain, such as:

- trust store
- identity store
- provider config store
- governance store
- scheduler state store

### Optional

Multiple state domains may share one physical database or directory if logical ownership still remains clear.

Compact storage is acceptable only when ownership boundaries remain explicit.

## 6. Validation On Read

### Mandatory

Persisted data must be validated when loaded.

### Mandatory

Invalid or corrupt state must fail safely.

Safe failure may include:

- rejecting invalid state
- resetting only the invalid portion when safe
- surfacing operator-visible diagnostics
- preserving unaffected valid state

### Recommended

Nodes should avoid silently accepting malformed persisted state.

## 7. Runtime Directories And File Layout

### Mandatory

Runtime state must live in a predictable runtime location.

### Recommended

Use a dedicated runtime directory and keep:

- mutable runtime state
- generated artifacts
- logs

separate from source-controlled documentation and source code.

### Recommended

The node should distinguish clearly between:

- committed configuration examples
- local runtime configuration
- generated runtime state
- generated logs and diagnostics

## 8. API Safety Rules

### Mandatory

APIs must not expose raw secrets or trust material.

### Mandatory

If a route returns configuration or credential-related state, it must return a safe summary rather than raw secret values.

### Recommended

Use patterns such as:

- `configured: true`
- `token_present: true`
- masked credential summaries
- sanitized provider configuration views

## 9. Logging Safety Rules

### Mandatory

Logs must not contain raw trust tokens, provider secrets, or other sensitive credentials in normal operation.

### Mandatory

Error handling must not leak sensitive configuration values.

### Recommended

Use dedicated masking or redaction helpers for:

- tokens
- grant identifiers when sensitive
- account secrets
- provider credentials

## 10. Diagnostics Artifact Rules

### Mandatory

If the node writes diagnostics artifacts, their location and sensitivity level must be clear.

### Mandatory

Diagnostics artifacts containing potentially sensitive material must not be treated as harmless public debug output.

### Recommended

Diagnostics artifacts should be:

- explicitly named
- documented
- separated from ordinary runtime state where possible

## 11. Rotation, Cleanup, And Reset Boundaries

### Mandatory

Reset and cleanup behavior must be explicit.

Nodes must not erase trust state, provider state, or operational records through ordinary startup paths.

### Recommended

If reset helpers exist, they should be separate intentional tools or scripts.

## 12. Governance And Budget-Related State

### Mandatory

If the node participates in governance, budget, or capability declaration behavior, it must persist enough local state to:

- understand current accepted state
- compare refresh or update events
- resume safely after restart
- present operator-visible readiness and blocker information

### Recommended

Nodes should keep governance and budget-related local state logically distinct from generic provider runtime state.

## 13. Provider State

### Mandatory

Provider-specific runtime state must be separated from generic node trust and lifecycle state.

### Mandatory

Provider credentials, tokens, and provider-local caches must not redefine or overwrite node-generic trust state.

### Recommended

Use provider-specific stores or namespaces under a clear provider boundary.

## 14. Scheduler And Background-Task State

### Mandatory

If the node runs recurring work, scheduler-related state must be persisted separately enough to support:

- safe restart
- operator visibility
- last success/failure tracking

### Recommended

Scheduler state should not be hidden inside unrelated provider or generic status blobs.

## 15. Documentation Expectations

### Mandatory

The node repository must document:

- key runtime paths
- key state files or stores
- configuration entrypoints
- sensitive-data boundaries

### Recommended

Documentation should make it clear which state is:

- safe to inspect
- sensitive
- generated
- expected to survive restart

## 16. Non-Compliance Signals

The node should be considered out of standard if:

- all persisted state is handled as one untyped blob
- trust and provider secrets appear in logs or API payloads
- configuration is loaded without validation
- restart-safe state is missing for trust or readiness-critical behavior
- provider state and node-generic state are blurred together
- reset behavior is hidden inside normal startup paths

## 17. Formal Compliance Checklist

Use this checklist during new-node design or standards review:

A node follows this standard when:

- state categories are explicit
- configuration is validated
- trusted and sensitive data are protected
- persistence ownership is modular
- persisted state is validated on read
- runtime paths are predictable
- APIs and logs expose only safe summaries
- restart-safe state exists for trust and readiness-critical behavior
