# Background Tasks And Internal Scheduler Standard

Last Updated: 2026-04-05 US/Pacific

## Purpose

This document defines the standard for node-local recurring work, internal scheduler behavior, and long-lived background runtime activity in Hexe nodes.

The goal is to ensure that new nodes can run recurring work safely, visibly, and in a way that remains compatible with Core scheduling, trust, governance, and budget rules.

## Rule Levels

- **Mandatory**
  Every Hexe node must satisfy these rules when it runs recurring or long-lived background work.
- **Recommended**
  Strong guidance that should usually be followed.
- **Optional**
  Acceptable patterns that may be used when helpful.

## Core Principle

The scheduler and background-task standard prioritizes:

- explicit ownership
- explicit state visibility
- safe startup and shutdown
- clear distinction between node-local scheduling and Core-owned scheduling
- compatibility with trust, governance, and budget enforcement

New nodes should model recurring work modularly, with explicit ownership and explicit task-state boundaries.

## 1. What Counts As Background Work

### Mandatory

The following kinds of work are considered background or scheduler-relevant behavior under this standard:

- polling loops
- recurring provider synchronization
- recurring governance or policy refresh work
- recurring health checks
- scheduled fetch or processing jobs
- long-lived heartbeat or lease loops
- recurring cleanup or reconciliation jobs

### Mandatory

If a node performs any of the above, it must explicitly model that behavior rather than treating it as invisible incidental code.

## 2. Node-Local Scheduler Versus Core Scheduler

### Mandatory

Nodes must distinguish between:

- Core-owned scheduling and admission
- node-local recurring work
- provider-specific recurring work

### Mandatory

Core remains the authority for platform scheduling, queue admission, and lease issuance where those apply.

### Mandatory

Node-local scheduler behavior must not redefine Core scheduling authority.

### Recommended

The node should document clearly whether each recurring task is:

- purely local recurring work
- a Core-leased execution flow
- a provider-specific poller
- a policy refresh loop

## 3. Scheduler Ownership

### Mandatory

Every recurring task or long-lived loop must have explicit runtime ownership.

The node must make clear:

- who starts the task
- who stops the task
- who reports task state
- who records task success and failure

### Recommended

Background work should be started only by the runtime orchestrator or a clearly delegated scheduler owner.

It should not be started ad hoc from unrelated modules.

## 4. Modular Structure For Background Work

### Mandatory

New nodes should implement background work in a modular way.

Scheduler ownership, task definitions, task state handling, and provider-specific recurring logic must not all collapse into one undifferentiated file.

### Recommended

Preferred modular boundaries include:

- scheduler owner or runtime owner
- task registry or task definitions
- task-state persistence
- provider-specific recurring task implementations
- health and reporting surface

### Optional

A small node may keep scheduler logic compact, but ownership and task boundaries must still remain explicit and separable.

Compact scheduler logic is a limited exception, not the default target for a new node.

## 5. Required Task State Visibility

### Mandatory

If a node runs recurring work, the node must expose operator-visible task state.

At minimum, task visibility should include:

- task identity
- current status
- last success timestamp
- last failure timestamp when applicable
- current error or last error when applicable
- whether the task is enabled

### Recommended

When relevant, the node should also expose:

- next planned run time
- last start time
- last completion time
- schedule description
- current attempt or retry state

## 6. Scheduler State Persistence

### Mandatory

Nodes with recurring work must persist the minimum state needed for safe restart and operator visibility.

The exact storage format may vary, but state must not exist only in memory if losing it would make the runtime opaque or unsafe.

### Recommended

Persist:

- loop enabled state
- loop active state where helpful
- last checked time
- last success time
- last failure time
- last known error
- task-specific checkpoint or slot state where required

## 7. Safe Startup And Shutdown

### Mandatory

Recurring work must have safe startup behavior.

The node must define:

- when tasks may start
- what trust or readiness conditions are required before they start
- what state is restored on startup

### Mandatory

Recurring work must have safe shutdown behavior.

The node must define:

- who cancels or stops tasks
- how in-flight work is finalized or abandoned
- how task state is recorded on shutdown

### Recommended

Nodes should avoid starting provider-affecting or Core-affecting recurring work before trust and required configuration are valid.

## 8. Scheduling Rules

### Mandatory

Every recurring task must have an explicit schedule model.

That schedule model may be:

- interval-based
- window-based
- event-assisted with periodic fallback
- lease-driven

### Mandatory

The schedule must be understandable enough that it can be surfaced to operators and documented.

### Recommended

Use operator-readable schedule names or schedule details rather than only raw internal timing constants.

### Recommended

When a node exposes scheduled task status in an operator UI, it should use consistent status color semantics:

- `idle` and `stopped` should render as orange
- `failing` should render as red
- all other scheduler task statuses should render as green
- `running` should use a darker green shade than other green scheduler statuses

### Recommended

When a node uses named local schedules, it should prefer a shared operator-visible schedule catalog.

Example schedule names include:

- `interval_seconds`
- `daily`
- `weekly`
- `4_times_a_day`
- `every_5_minutes`
- `hourly`
- `bi_weekly`
- `monthly`
- `every_other_day`
- `twice_a_week`
- `on_start`
- `every_10_seconds`

`interval_seconds` is the general-purpose named schedule for tasks that require an integer-second cadence not otherwise covered by a shared named slot.

Short interval schedules are acceptable when the work is lightweight, state-visible, and operationally justified.

## 8A. Mandatory Baseline Recurring Tasks

### Mandatory

Every Hexe node must explicitly model these node-local recurring tasks:

- heartbeat
- telemetry
- operational MQTT health

### Mandatory

These tasks must be visible to operators through structured scheduler task state.

### Recommended

Default local schedule guidance is:

- heartbeat: every 5 seconds
- telemetry: every 60 seconds
- operational MQTT health:
  - every 10 seconds while the node is trusted, degraded, or in an active recovery window
  - every 10 seconds for 5 minutes after backend startup
  - every 10 seconds for 5 minutes after return to fully operational
  - every 5 minutes while the node is stably operational

Nodes may extend or override these cadences only when the runtime behavior remains documented and operator-visible.

## 9. Failure Handling

### Mandatory

Recurring task failures must not disappear silently.

Failures must result in one or more of:

- task state update
- operator-visible degraded signal
- retry state update
- logged actionable error

### Mandatory

Repeated failure must be distinguishable from one-off failure when it materially affects readiness or operator action.

### Recommended

Nodes should decide explicitly which recurring-task failures:

- are informational only
- should block readiness
- should trigger degraded state

## 10. Readiness Interaction

### Mandatory

If a recurring task is required for operational readiness, that requirement must be represented explicitly in the node’s readiness model.

### Mandatory

If a recurring task is not readiness-critical, it should not silently block the node from becoming operational.

### Recommended

Nodes should distinguish:

- required scheduler tasks
- operational-but-non-blocking maintenance tasks
- optional diagnostics tasks

## 11. Core-Leased Work Compatibility

### Mandatory

When a node participates in Core-scheduled execution through lease or worker-style APIs, it must remain compatible with the canonical Core lease lifecycle.

This includes:

- work request or claim
- heartbeat
- progress reporting
- completion or failure
- revoke handling

### Mandatory

Node-internal abstractions must not break compatibility with the Core-owned lease contract.

### Recommended

Lease-driven work should be modeled distinctly from purely local recurring work, even if both are managed by the same runtime owner.

## 12. Budget And Governance Interaction

### Mandatory

Recurring work that performs execution, provider usage, or policy-sensitive actions must respect:

- trust state
- governance constraints
- budget policy where applicable

### Mandatory

Nodes must not continue execution-style background work as if fully operational when governance or trust state makes that unsafe.

### Recommended

Budget-aware recurring work should keep enough state to support:

- local enforcement
- retry visibility
- later usage reporting or reconciliation

## 13. Notification And Operator Signaling

### Recommended

Nodes should use structured operator signaling for meaningful background-task problems.

This may include:

- local UI indicators
- status payloads
- notification requests to Core when implemented and appropriate

### Mandatory

Operator signaling must not leak secrets or unsafe internals.

## 14. API And UI Expectations

### Mandatory

If the node exposes scheduler or recurring-task behavior in API or UI, the representation must be structured and operator-readable.

### Recommended

Use fields such as:

- scheduler status
- task list
- task state
- schedule name
- schedule detail
- last run timestamps
- last error

## 14A. Expected Scheduled Tasks Card

### Mandatory

If a node has an operator dashboard or operational-status page, it must include a dedicated `Scheduled Tasks` card or page section for recurring scheduler work.

This view must be separate from generic diagnostics text dumps.

### Mandatory

The `Scheduled Tasks` view must show one row per recurring task.

At minimum, each row must include:

- task display name
- task kind
- schedule name
- schedule detail
- current status
- last success time
- last failure time
- next run time
- last error

### Mandatory

The task list must use structured table-style presentation or an equivalent columnar layout that lets operators compare tasks quickly.

Free-form paragraph rendering is not sufficient.

### Recommended

Default column order should be:

- Task
- Kind
- Schedule
- Status
- Last Success
- Last Failure
- Next Run
- Last Error

### Recommended

The task list should sort by display name or a stable operator-friendly order.

Task order should not appear random between renders.

### Recommended

The `Schedule` column should render both:

- the machine-stable schedule name such as `4_times_a_day`
- the human-readable schedule detail such as `00:00, 06:00, 12:00, 18:00`
- a friendly operator label such as `4 Times A Day`

### Recommended

The `Kind` column should use friendly operator labels rather than raw internal identifiers when a user-facing mapping exists.

For example:

- `runtime_recurring` -> `Runtime`
- `provider_recurring` -> `Provider`
- `system_recurring` -> `System`

The raw machine kind may still be exposed through API or diagnostics payloads.

### Recommended

The `Status` column should use a visible badge or pill, not plain text only.

Status-color semantics should follow this standard:

- `idle` and `stopped` -> orange
- `failing` -> red
- `running`, `scheduled`, and `healthy` -> green
- `running` should use a darker green than other green scheduler states

### Recommended

When a schedule catalog exists, the `Scheduled Tasks` view should also include a schedule legend or catalog list below the task table.

That legend should show:

- schedule name
- schedule detail

### Recommended

When a schedule legend is shown, it should be sorted by effective duration from shortest to longest.

The general-purpose `interval_seconds` entry should sort last because it is parameterized rather than fixed-duration.

### Mandatory

If no scheduler task state is available yet, the view must render an explicit empty state such as:

- `No scheduled task data is available yet.`

The view must not silently disappear.

### Recommended

Timestamps should be operator-readable in local time formatting where the UI already follows local-time conventions.

### Recommended

The card or page subtitle should make clear that the view represents:

- scheduler-driven background jobs
- current cadence
- latest execution state

## 15. Non-Compliance Signals

The node should be considered out of standard if:

- recurring work has no clear owner
- tasks start implicitly from unrelated code
- recurring-task state disappears on restart without design justification
- failures are only visible in logs
- readiness depends on recurring work but the node does not expose that dependency
- Core-leased work is implemented incompatibly with the Core lease lifecycle

## 16. Formal Compliance Checklist

Use this checklist during new-node design or standards review:

A node follows this standard when:

- recurring work has explicit ownership
- task state is visible and persisted appropriately
- startup and shutdown rules are explicit
- schedule behavior is understandable
- failures are surfaced clearly
- readiness interaction is explicit
- Core-leased work remains compatible where applicable
