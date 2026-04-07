# Frontend Standard

Last Updated: 2026-04-04 US/Pacific

## Purpose

This document defines the frontend standard for Hexe nodes.

The goal is to standardize operator-facing outcomes, frontend responsibilities, and UI consistency while making modular frontend structure the default for any new node.

## Rule Levels

- **Mandatory**
  Every Hexe node frontend must satisfy these rules.
- **Recommended**
  Strong guidance that should usually be followed.
- **Optional**
  Acceptable patterns that may be used when helpful.

## Core Principle

The frontend standard prioritizes:

- operator clarity
- lifecycle visibility
- setup visibility
- operational visibility
- recovery visibility
- modular growth paths

over:

- identical routing structure
- identical component counts
- rigid one-shape-only layouts

New nodes should use a modular frontend structure by default.

## 1. Required Frontend Responsibilities

### Mandatory

Every node frontend must provide operator-visible access to:

- node status
- onboarding or setup progress
- trust or pairing state
- operational readiness or blocker state
- provider or capability setup status where applicable
- degraded or backend-unavailable states

### Recommended

The UI should make these areas clearly discoverable without requiring the operator to understand the internal architecture of the node.

## 2. Required Operator Flows

### Mandatory

Every node frontend must support the flows that match the node’s implemented capabilities:

- initial setup
- onboarding progress monitoring
- trust and readiness visibility
- provider setup visibility where applicable
- operational dashboard access after setup
- common recovery actions for non-terminal failures

### Recommended

Setup should feel like a guided operational flow, not just a collection of disconnected forms.

## 3. Lifecycle And Status Visibility

### Mandatory

The frontend must present current node lifecycle and status clearly.

This includes, where applicable:

- current lifecycle stage
- onboarding state
- trust state
- capability state
- governance/readiness state
- provider state
- background-task state

### Recommended

Status should be understandable at a glance using:

- badges
- stage cards
- summary strips
- blocker lists

Text labels should remain readable without requiring raw JSON inspection.

## 4. Setup And Onboarding UX

### Mandatory

The frontend must support operator understanding of the onboarding process.

The UI must expose, where implemented:

- required configuration inputs
- current onboarding status
- approval URL or approval step visibility
- node identity and pairing state when known
- recovery or restart-setup action when allowed

### Recommended

Setup should show progression and blockers in a stage-oriented way.

### Mandatory

Provider setup must not visually replace core node onboarding. It may extend setup, but it must remain distinct from trust establishment.

## 5. Operational Dashboard Requirements

### Mandatory

Each node frontend must provide an operational view after setup.

The operational view must make it possible to inspect:

- current status
- recent blockers or degraded conditions
- readiness-related state
- provider state where applicable
- service or runtime actions where supported

### Recommended

Operational UI should separate:

- setup concerns
- runtime concerns
- diagnostics concerns

even if they share one application shell.

## 6. Error And Recovery UX

### Mandatory

The frontend must represent backend failures and degraded states explicitly.

This includes:

- backend unavailable state
- invalid or incomplete setup state
- readiness blockers
- failed actions
- long-running operation feedback

### Recommended

Errors should guide the operator toward the next action rather than only showing failure text.

## 7. Frontend Structure Expectations

### Mandatory

The frontend must have a clear ownership boundary for:

- API access
- status/state shaping
- setup/onboarding presentation
- operational presentation

These boundaries do not require separate directories, but they must be recognizable in code.

### Recommended

Prefer:

- feature-oriented organization
- a shared API wrapper or client layer
- shared UI primitives for status and cards
- route or mode separation between setup and operational views

### Optional

Allowed implementation shapes include:

- a modular feature-based structure
- a hybrid approach where growth areas are split first
- a mostly centralized app only when the UI is still small and ownership boundaries remain clear

Compact frontend structure is a limited exception, not the standard target.

## 8. API Access Layer

### Mandatory

Frontend calls to the backend must be handled in a predictable and reusable way.

The frontend must have a clear API access pattern for:

- base URL handling
- request defaults
- JSON parsing
- error normalization

### Recommended

Use a central API wrapper or a small API client module instead of raw fetch calls duplicated throughout the UI.

## 9. Visual Consistency Rules

### Mandatory

The frontend must use consistent visual patterns for:

- status indicators
- action buttons
- stage progress
- warning or blocker callouts
- unavailable or degraded states

### Recommended

Use shared design tokens, shared badge styles, and shared status-tone conventions.

The frontend should avoid creating a different status language in each section of the node UI.

## 10. Responsive And Operator-Friendly Design

### Mandatory

The frontend must remain usable on both desktop and smaller screens.

Critical setup and operational status information must remain readable without layout breakage.

### Recommended

Prefer:

- summary-first layouts
- clear spacing and grouping
- visible hierarchy between setup, operational, and diagnostic surfaces

## 11. Diagnostics Visibility

### Mandatory

If a node exposes diagnostics, the frontend must present them in a way that supports operators without requiring raw implementation knowledge.

### Recommended

Detailed JSON or low-level data may be included, but should sit behind a readable summary layer.

## 12. Allowed Implementation Variants

### Preferred variant: Modular frontend

This is the default target for new nodes.

Typical characteristics:

- feature folders or clearly separated view domains
- shared UI primitives
- route or mode separation
- API helper layer
- clear distinction between setup, operational, and diagnostics surfaces

### Limited exception: Compact frontend

This is allowed only when the UI is still small and the frontend can remain readable without blurring responsibility boundaries.

Typical characteristics:

- one main app file with clearly separated sections
- typed or structured backend contracts
- limited surface area

### Mandatory rule across all variants

- required operator flows must be present
- modular responsibility boundaries must remain clear
- lifecycle and readiness visibility must be clear
- degraded states must be explicit
- API access patterns must be consistent

## 13. Non-Compliance Signals

The frontend should be considered out of standard if:

- onboarding state is hidden or unclear
- provider setup is conflated with node trust setup
- readiness blockers are only visible in raw JSON
- backend-unavailable states are poorly handled
- the operator has no clear post-setup operational view
- UI structure makes status ownership impossible to understand
- compact structure has grown to the point that setup, operational, and diagnostics ownership are blurred

## 14. Formal Compliance Checklist

Use this checklist during new-node design or standards review:

A node frontend is aligned with this standard when:

- it exposes setup and operational flows clearly
- lifecycle and readiness state are visible
- degraded and unavailable states are explicit
- provider or capability setup is visible where applicable
- API access is handled consistently
- status language is visually consistent
- the UI remains usable across screen sizes
