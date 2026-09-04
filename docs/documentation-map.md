# Documentation Map

Status: Implemented

This repository uses root `docs/` as the canonical documentation tree. Use this map to decide whether a file is active source-of-truth material, historical context, or future planning.

## Active Source Of Truth

- `docs/overview.md` and `docs/architecture.md`: current platform boundary summaries.
- `docs/core/`: current Core API, frontend, config, store, MQTT authority, node governance, and addon lifecycle documentation.
- `docs/supervisor/`: current Supervisor API, runtime, service configuration, resource history, and host-local lifecycle documentation.
- `docs/nodes/`: current node onboarding, trust, capability, governance, telemetry, UI manifest, and node contract documentation, excluding `future-dev/`.
- `docs/addons/README.md`, `docs/addons/embedded/`, and current addon/MQTT contracts.
- `docs/mqtt/`: current MQTT topic, authority, notification, and router ownership documentation.
- `docs/config/`: generated and registry-backed environment configuration docs.
- `docs/json_schema/`: current schema catalog.
- `docs/standards/`: current authoring and implementation standards.
- `docs/operators-guide.md` and `docs/development-guide.md`: current operator and developer entrypoints.

## Historical Or Archive Context

- `docs/migration/`: migration logs, audits, and phase completion notes.
- `docs/Upgrades/`: prior upgrade/design material retained for context.
- `docs/addons/standalone-archive/`: historical standalone-addon design and incident material.
- `docs/temp-ai-node/`: temporary AI-node mapping and gap reports retained as source context, not as current Core contracts.
- Ignored local `supervisor/docs/` files: archive/operator notes from the Supervisor mirror. These files are not tracked source of truth and must not carry active task workflow state.

## Future Planning

- `docs/nodes/future-dev/`: planned or not-yet-developed node UI migration material.
- `docs/core/feature-request-*.md`: feature requests, not implemented behavior unless an active doc says otherwise.

## Reference Artifacts

- `docs/screenshots/`: screenshot capture notes and visual references. These files are not product-contract source of truth.

## Workload Boundary Reminder

Active docs must not describe Core as owning job queueing, job leasing, worker execution, or per-job budget usage-report APIs. Core owns internal recurring maintenance scheduling and policy/control-plane surfaces. Supervisor and Nodes are the runtime/execution boundaries.
