# Synthia Core Documentation

This page is the navigation hub for the Synthia Core repository documentation. Use it to find the right document before going into subsystem-specific detail.

This file is the canonical documentation index for the repository. The older `document-index.md` and `platform-architecture.md` documents were merged into this structure and archived.

## Start Here

- [../README.md](../README.md)
  Repository entry point with the high-level explanation of what Synthia Core is, what it includes, and how to run or install it.
- [overview.md](./overview.md)
  Platform-level overview for readers who need wider Synthia context first.
- [architecture.md](./architecture.md)
  Internal architecture of the Synthia Core repository, including subsystem boundaries and control flows.

## Core Platform

- [fastapi/README.md](./fastapi/README.md)
  Backend documentation hub for the FastAPI control plane.
- [fastapi/core-platform.md](./fastapi/core-platform.md)
  Core control-plane responsibilities, ownership boundaries, and readiness model.
- [fastapi/api-reference.md](./fastapi/api-reference.md)
  API route-family reference for the backend mounted by Core.
- [frontend/README.md](./frontend/README.md)
  Frontend documentation hub for the React operator UI.
- [frontend/frontend-and-ui.md](./frontend/frontend-and-ui.md)
  Frontend structure and Core-managed UI surfaces.
- [fastapi/auth-and-identity.md](./fastapi/auth-and-identity.md)
  Authentication and identity references for admin, service, and platform actors.
- [fastapi/telemetry-and-usage.md](./fastapi/telemetry-and-usage.md)
  Usage telemetry API and storage reference for service-reported accounting data.

## Runtime and Messaging

- [mqtt/README.md](./mqtt/README.md)
  Messaging documentation hub for MQTT and notifications.
- [mqtt/mqtt-platform.md](./mqtt/mqtt-platform.md)
  MQTT authority, runtime, bootstrap, and principal lifecycle documentation.
- [mqtt/topics.md](./mqtt/topics.md)
  Canonical MQTT topic families and topic-scope rules derived from runtime code.
- [mqtt/notifications.md](./mqtt/notifications.md)
  Notification topics, routing behavior, local consumer rules, and bridge-owned external payloads.
- [supervisor/README.md](./supervisor/README.md)
  Standalone runtime and supervision documentation hub.
- [supervisor/runtime-and-supervision.md](./supervisor/runtime-and-supervision.md)
  Runtime ownership, supervision boundaries, and standalone runtime behavior.
- [fastapi/data-and-state.md](./fastapi/data-and-state.md)
  Persistent and runtime state references used across the platform.
- [overview.md](./overview.md)
  Includes the higher-level role of MQTT and runtime boundaries in the platform.

## Addons and Nodes

- [addons/README.md](./addons/README.md)
  Canonical addon documentation hub for embedded and standalone addons.
- [addons/addon-platform.md](./addons/addon-platform.md)
  Embedded and standalone addon models, lifecycle, registry, and store relationships.
- [addons/addon-lifecycle.md](./addons/addon-lifecycle.md)
  Code-verified addon lifecycle and install-session state model.
- [addon-embedded/README.md](./addon-embedded/README.md)
  Embedded addon runtime notes and references back to the canonical addon docs.
- [addon-standalone/README.md](./addon-standalone/README.md)
  Standalone addon runtime, packaging, and compatibility references.
- [nodes/README.md](./nodes/README.md)
  Trusted-node documentation hub.
- [nodes/node-lifecycle.md](./nodes/node-lifecycle.md)
  Trusted-node onboarding, registration, governance, and telemetry lifecycle.
- [nodes/node-onboarding-registration-architecture.md](./nodes/node-onboarding-registration-architecture.md)
  Global onboarding and registration architecture for trusted nodes.
- [nodes/node-phase2-lifecycle-contract.md](./nodes/node-phase2-lifecycle-contract.md)
  Trusted-node capability, governance, and operational lifecycle references.
- [temp-ai-node/README.md](./temp-ai-node/README.md)
  Temporary home for AI-node-specific compatibility documents and migration notes.

## Scheduler and Workers

- [scheduler/README.md](./scheduler/README.md)
  Scheduler landing page for queueing and lease-based execution docs.
- [scheduler/job-model.md](./scheduler/job-model.md)
  Queue job, lease, and job-intent model reference.
- [workers/README.md](./workers/README.md)
  Worker landing page for execution helper docs.
- [workers/worker-runtime.md](./workers/worker-runtime.md)
  Worker runner lifecycle, handler registry, and scheduler interaction reference.

## Operations and Development

- [operators-guide.md](./operators-guide.md)
  Operational guidance and runbook-style documentation.
- [development-guide.md](./development-guide.md)
  Development and documentation maintenance guidance for this repository.
- [ROADMAP.md](./ROADMAP.md)
  Active planning input for ongoing work.
- [documentation-migration-map.md](./documentation-migration-map.md)
  Documentation consolidation and migration tracking.

## Standards And Reference

- [standards/README.md](./standards/README.md)
  Platform standards and specification references that may include planned behavior.
- [addon-standalone/addon-manifest.schema.json](./addon-standalone/addon-manifest.schema.json)
  Standalone addon manifest schema reference.
- [addon-standalone/desired.schema.json](./addon-standalone/desired.schema.json)
  Standalone desired-state schema reference.
- [addon-standalone/runtime.schema.json](./addon-standalone/runtime.schema.json)
  Standalone runtime-state schema reference.
