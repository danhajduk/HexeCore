# Node Standard Creation Tasks

Last Updated: 2026-04-04 US/Pacific

## Purpose

Create a canonical Hexe node standard that requires the least adaptation across both currently inspected repositories:

- `HexeAiNode` at `/home/dan/Projects/HexeAiNode`
- `HexeEmail` at `/home/dan/Projects/HexeEmail`

This file is a task list for the standard-definition work. It is not the standard itself.

## Working Goal

Define a shared node standard that:

- preserves the common node lifecycle and Core integration model already present in both repositories
- avoids forcing `HexeEmail` into the full package depth of `HexeAiNode`
- avoids forcing `HexeAiNode` back into a flatter single-service layout
- standardizes boundaries, contracts, naming, and required folders before standardizing internal implementation details
- separates what must be mandatory for all nodes from what can remain node-specific

## Initial Verified Findings

### Shared foundations already present in both repositories

- Both repositories expose a FastAPI backend entrypoint:
  - `HexeAiNode`: `src/ai_node/main.py`
  - `HexeEmail`: `src/main.py`
- Both repositories include a React + Vite frontend:
  - `HexeAiNode`: `frontend/package.json`
  - `HexeEmail`: `frontend/package.json`
- Both repositories include `scripts/` with stack bootstrap and systemd templates.
- Both repositories include onboarding and trust-oriented runtime behavior.
- Both repositories include capability declaration and governance-related flows.
- Both repositories maintain local runtime state and local docs.
- Both repositories already follow the broader Core node model documented under `docs/Core-Documents/nodes/`.

### Structural differences that the standard must accommodate

- `HexeAiNode` uses a deeper package-based backend layout under `src/ai_node/` with subsystem folders such as:
  - `runtime/`
  - `core_api/`
  - `capabilities/`
  - `registration/`
  - `trust/`
  - `persistence/`
  - `providers/`
- `HexeEmail` uses a flatter backend layout with key orchestration concentrated in:
  - `src/service.py`
  - `src/main.py`
  - `src/core/`
  - `src/providers/gmail/`
- `HexeAiNode` frontend is increasingly split into feature folders under `frontend/src/features/`.
- `HexeEmail` frontend currently keeps a large amount of UI logic inside `frontend/src/App.jsx`.
- `HexeEmail` already includes internal scheduled/background Gmail work inside `NodeService`.
- `HexeAiNode` includes scheduler-related integration with Core leasing and runtime services, but its local backend organization is more runtime/module driven than provider-pipeline driven.

### Standard design implication from the initial check

The shared standard should prefer:

- required top-level domains and contracts
- optional depth inside those domains
- mandatory naming and responsibility boundaries
- recommended, not mandatory, internal decomposition patterns

It should not require both repositories to adopt the same internal file count or the same exact package depth.

## Main Deliverable To Produce After This Task List

Create a detailed canonical node standard document under `docs/Core-Documents/nodes/` that defines:

- mandatory node architecture layers
- allowed implementation variants
- required API and lifecycle contracts
- frontend structure and UX expectations
- scripts and operations expectations
- scheduler/background-task rules
- onboarding requirements
- documentation and testing expectations

## Task List

## 1. Confirm The Standard Boundary

- Define exactly what the node standard governs:
  - repository structure
  - runtime responsibilities
  - Core-facing contracts
  - UI expectations
  - operational tooling
  - testing and docs
- Define what the node standard does not govern:
  - provider-specific pipelines
  - domain-specific business logic
  - internal algorithm choices
  - provider-specific persistence details
- Establish the standard as a node-platform standard, not an AI-node-only or email-node-only standard.

## 2. Build A Cross-Repo Architecture Comparison Matrix

- Create a side-by-side comparison table for:
  - backend structure
  - frontend structure
  - API surface layout
  - onboarding lifecycle
  - trust persistence
  - capability declaration flow
  - governance sync
  - background jobs
  - scripts and systemd integration
  - testing layout
  - docs layout
- Mark each area as:
  - shared already
  - compatible with small normalization
  - materially divergent
- Use that matrix to decide what becomes:
  - mandatory
  - recommended
  - optional
  - node-specific

## 3. Define The Canonical Backend Structure

- Standardize the required backend responsibility domains that every node must have, regardless of package depth:
  - entrypoint
  - lifecycle
  - onboarding/registration
  - trust and identity
  - Core API clients
  - capabilities
  - governance/readiness
  - runtime services
  - provider integrations
  - persistence/state stores
  - diagnostics/logging
  - security/redaction
- Decide the minimum acceptable backend layout pattern.
  Proposed direction from the initial check:
  - allow either a package-rich layout like `HexeAiNode`
  - or a compact layout like `HexeEmail`
  - but require those domains to be clearly identifiable in code ownership and documentation
- Define whether the standard should require:
  - one primary orchestration service
  - or multiple subsystem services
  - or allow both as long as boundaries are documented
- Define naming conventions for backend modules:
  - `main`
  - `service` or `runtime`
  - `core` or `core_api`
  - `providers`
  - `persistence` or `state_store`
  - `config`
- Define how node-specific providers should be isolated from node-generic runtime code.
- Define how runtime state models should be separated from HTTP request/response models.
- Define when a node should split a large `service.py` into subsystems.
- Define required validation, error handling, and safe logging expectations.

## 4. Define The Canonical Frontend Structure And Design Standard

- Define the minimum frontend layers every node UI must provide:
  - app shell
  - setup/onboarding flow
  - operational dashboard
  - provider or capability setup area when relevant
  - diagnostics or operator visibility surface when relevant
- Define the preferred frontend structure:
  - feature-based organization
  - shared theme tokens
  - reusable UI primitives
  - route or mode separation
- Decide what is mandatory versus recommended for UI decomposition.
  Likely direction:
  - require feature/domain separation at the documentation level
  - recommend breaking oversized `App.jsx` files into feature modules
  - do not make deep component fragmentation mandatory for small nodes
- Define frontend design rules shared across nodes:
  - status-first operator UX
  - setup progress visibility
  - clear lifecycle and trust state display
  - strong degraded/error-state handling
  - responsive layouts
  - shared theme token approach
- Define the standard for frontend-to-backend API access:
  - central API client or fetch wrapper
  - error normalization
  - polling/refresh conventions
  - correlation and diagnostics exposure where relevant
- Define UI consistency rules for:
  - lifecycle badges
  - status chips
  - stage cards
  - action buttons
  - backend unavailable states
- Define when a node UI may remain simple and when it must be split into feature sections.

## 5. Define The Canonical API Structure

- Inventory the shared API categories already visible across both nodes:
  - health
  - node status
  - UI bootstrap/config
  - onboarding actions
  - capability configuration and declaration
  - governance status and refresh
  - services status and restart
  - provider-specific APIs
  - runtime execution or preview APIs
- Define the required API namespace conventions for all nodes.
  Items to settle:
  - whether `/api/node/*` must be canonical
  - whether legacy convenience routes may still exist
  - whether UI-prefixed routes such as `/ui/*` remain allowed
- Define mandatory API contract groups:
  - `GET /api/health` or equivalent
  - node status/bootstrap/config
  - onboarding start/status/restart as applicable
  - capability declaration/config
  - governance/readiness
  - service control if local restart controls are exposed
- Define rules for provider-specific APIs so provider routes do not pollute node-generic contracts.
- Define request/response schema expectations:
  - JSON-only
  - typed models
  - normalized error payloads
  - backward-compatible naming where needed
- Define whether OpenAPI, JSON schema, or contract docs become mandatory for node-standard APIs.
- Define compatibility rules for routes already used by existing UIs.

## 6. Define The Canonical Scripts And Operations Structure

- Compare current script categories in both repos:
  - bootstrap/install
  - stack control
  - restart helpers
  - run-from-env
  - dev/start scripts
  - acceptance/status/reset helpers
- Define the minimum required script set for every node.
  Likely shared baseline:
  - `bootstrap.sh`
  - `run-from-env.sh`
  - `stack-control.sh`
  - `restart-stack.sh`
  - `stack.env.example`
  - `scripts/systemd/<backend>.service.in`
  - `scripts/systemd/<frontend>.service.in`
- Decide which scripts are optional but recommended:
  - `dev.sh`
  - `start.sh`
  - `status.sh`
  - acceptance scripts
  - reset-runtime helpers
- Define script naming conventions and environment variable conventions.
- Define the standard rendering approach for systemd user services.
- Define operational logging expectations for scripts.
- Define the standard for local stack startup so frontend/backend commands are externally configurable.

## 7. Define The Background Tasks And Internal Scheduler Standard

- Document the different current realities:
  - `HexeEmail` has explicit internal scheduled Gmail fetch work and pipeline state
  - `HexeAiNode` has runtime task execution, capability workflows, readiness, and scheduler lease integration
- Define a shared node-level scheduler standard that works for both:
  - nodes may have internal scheduled/background work
  - scheduled work must remain visible, inspectable, and stateful
  - scheduled work must not bypass Core trust/governance requirements
- Define the canonical concepts for internal node scheduler design:
  - scheduler loop ownership
  - persisted scheduler state
  - task registration
  - task schedule description
  - task last-run/next-run/error reporting
  - safe startup/resume behavior
  - disable/enable controls
- Define what every node with background work must expose:
  - scheduler status
  - per-task state
  - last success/error timestamps
  - operator-readable schedule descriptions
- Define the difference between:
  - Core-owned scheduled work and admission
  - node-local recurring background tasks
  - provider-specific polling loops
- Define whether the standard needs:
  - a dedicated scheduler module
  - or only a documented scheduler responsibility boundary
- Define failure and recovery rules for background tasks.

## 8. Define The Canonical Onboarding Process Standard

- Compare current onboarding implementations and extract common invariants:
  - operator-configured Core endpoint
  - onboarding session creation
  - approval URL surfacing
  - finalize polling or approval completion handling
  - trust material persistence
  - restart-safe resume
  - transition into trusted runtime behavior
- Define the mandatory onboarding stages that all nodes must model.
- Align the node standard with existing canonical Core node lifecycle docs under `docs/Core-Documents/nodes/`.
- Define required local persistence for onboarding and trust state.
- Define required operator-visible onboarding metadata:
  - session ID
  - approval URL
  - node identity summary
  - current onboarding status
  - failure reason if onboarding stalls or fails
- Define required recovery controls:
  - restart setup
  - re-run finalize checks
  - safe trust resume on restart
- Define whether all nodes must expose onboarding through both API and UI.
- Define the standard for approval polling, timeout handling, and terminal states.

## 9. Define Capability, Governance, And Readiness Requirements

- Compare the current capability flow in both repos.
- Define which parts must be mandatory for all nodes:
  - local capability selection or capability resolution
  - declaration submission to Core
  - persisted accepted state
  - governance refresh/sync
  - operational readiness evaluation
- Define how node-specific capability logic may differ while still fitting a shared contract.
- Define how blocking reasons, readiness flags, and degraded-state causes should be exposed.
- Define whether capability setup should be a first-class UI stage for all nodes.

## 10. Define Persistence And Runtime Data Standards

- Inventory current runtime storage patterns:
  - `.run/*.json` style files in `HexeAiNode`
  - runtime stores and SQLite-backed provider data in `HexeEmail`
- Define the shared persistence standard at the category level:
  - trust material
  - node identity
  - operator config
  - capability state
  - governance state
  - provider state
  - scheduler/background-task state
  - logs and diagnostics artifacts
- Define what storage locations should be standardized.
- Define what file formats may vary.
- Define validation and corruption-handling expectations.
- Define sensitive data handling and masking rules.

## 11. Define Provider Integration Boundary Rules

- Use the initial check to keep provider-specific logic isolated.
- Define the minimum provider boundary:
  - provider registry or equivalent
  - provider adapter/service contract
  - provider-specific storage
  - provider-specific APIs under a clear namespace
- Ensure the node standard allows:
  - AI-model-provider nodes
  - Gmail/email-provider nodes
  - future nodes with other provider families
- Define how provider-specific onboarding or credential setup can coexist with generic node onboarding.

## 12. Define Testing Expectations For Standard Compliance

- Compare current testing layouts in both repositories.
- Define required test categories for every node:
  - backend API tests
  - onboarding flow tests
  - trust/capability/governance state tests
  - provider boundary tests where applicable
  - scheduler/background-task tests where applicable
  - frontend smoke or rendering tests where UI complexity justifies them
- Define which tests become mandatory for standard compliance and which are recommended.
- Define whether a future node-standard checklist should include test evidence.

## 13. Define Documentation Requirements For Every Node

- Define the minimum doc set a node repository must maintain.
  Likely baseline:
  - README
  - architecture document
  - setup/run document
  - API contract or API reference
  - provider setup docs where applicable
  - operations/runbook
- Define which docs should live in node repos and which should live in Core docs.
- Define how node repos should link back to canonical Core node contracts.
- Define how the standard itself should cross-reference existing node lifecycle, onboarding, and scheduled-work Core documents.

## 14. Define Naming, Terminology, And Compatibility Rules

- Normalize terminology differences such as:
  - node status vs onboarding status
  - provider setup vs capability setup
  - runtime service vs node service
  - Core API clients vs core clients
- Define canonical names for:
  - backend entrypoint
  - node service/runtime orchestrator
  - provider integrations
  - state stores
  - service control APIs
  - scheduler/background tasks
- Define how compatibility-era names may remain in place without breaking the new standard.

## 15. Produce The Final Node Standard Document

- Draft the standard in a new `docs/Core-Documents/nodes/` document.
- Structure it so teams can read it as both:
  - an architecture standard
  - a repo implementation checklist
- Mark each rule clearly as:
  - Mandatory
  - Recommended
  - Optional
- Include examples from both repositories where useful.
- Ensure the standard is written to minimize adaptation work for both currently inspected node repositories.

## 16. Produce A Repo Adaptation Gap Appendix

- After the standard is written, create a gap assessment for:
  - `HexeAiNode`
  - `HexeEmail`
- For each repo, identify:
  - already compliant areas
  - small changes needed
  - larger refactors that should remain optional
- Ensure the final standard does not accidentally make one current repo non-viable without significant rewrite.

## Suggested Execution Order

1. Confirm standard scope and non-goals.
2. Build the cross-repo comparison matrix.
3. Lock backend, frontend, and API minimum structure rules.
4. Lock scripts, scheduler/background-task, and onboarding rules.
5. Lock persistence, provider boundary, testing, and docs rules.
6. Write the standard document.
7. Write the repo gap appendix against both repositories.

## Acceptance Criteria For This Task List Phase

- A new task-list file exists in `docs/Core-Documents/nodes/`.
- The task list is grounded in verified structures from both repositories.
- The task list explicitly covers:
  - backend structure
  - frontend structure and design
  - API structure
  - scripts
  - background tasks and internal scheduler
  - onboarding
  - additional areas found during the initial inspection
- The task list is biased toward minimum adaptation across both repositories.
