# Synthia MQTT Topic Tree (Canonical)

Last Updated: 2026-03-09 06:57 US/Pacific

## Contract

This document is the canonical topic-structure source of truth for Synthia MQTT in this repository.

Control-plane rule:
- MQTT topics are async visibility/distribution transport.
- Deterministic control transactions remain HTTP API-first.

## Top-Level Reserved Families

| Family | Owner | Phase 1 Status | Notes |
|---|---|---|---|
| `synthia/bootstrap/...` | Core | Implemented (core bootstrap topic) | Anonymous bootstrap-only subscribe contract |
| `synthia/core/...` | Core | Partially Implemented | `synthia/core/mqtt/info` implemented |
| `synthia/system/...` | Core Platform | Reserved | Protected namespace |
| `synthia/supervisor/...` | Core Platform | Reserved | Protected namespace |
| `synthia/scheduler/...` | Core Platform | Reserved | Protected namespace |
| `synthia/policy/...` | Core Policy | Implemented | Grant/revocation distribution topics implemented |
| `synthia/telemetry/...` | Core Platform | Reserved | Protected namespace |
| `synthia/services/...` | Core Services | Partially Implemented | `synthia/services/+/catalog` subscription implemented |
| `synthia/addons/<addon_id>/...` | Addon Principal + Core policy | Implemented (announce/health + scoped publish rules) | Addon publish must stay in addon namespace unless explicitly approved reserved access |
| `synthia/nodes/<node_id>/...` | Synthia Node Principal | Not developed | Reserved planned family for Phase 1+ |

## Implemented Lifecycle/Platform Topics

| Topic | Publisher | Subscriber(s) | Retained | QoS | Status |
|---|---|---|---|---|---|
| `synthia/bootstrap/core` | Core startup reconcile | Anonymous + platform clients | `true` | `1` | Implemented |
| `synthia/core/mqtt/info` | Core MQTT manager/startup reconcile | Core + observers | `true` | `1` | Implemented |
| `synthia/addons/+/announce` | Addons | Core MQTT manager | producer-defined | `1` (Core subscription) | Implemented |
| `synthia/addons/+/health` | Addons | Core MQTT manager | producer-defined | `1` (Core subscription) | Implemented |
| `synthia/services/+/catalog` | Services | Core MQTT manager | producer-defined | `1` (Core subscription) | Implemented |
| `synthia/policy/grants/{service}` | Core policy | Consumers/services | `true` | `1` | Implemented |
| `synthia/policy/revocations/{consumer_addon_id}` | Core policy | Consumers/services | `true` | `1` | Implemented |
| `synthia/policy/revocations/{grant_id}` | Core policy | Consumers/services | `true` | `1` | Implemented |
| `synthia/policy/revocations/{id}` (legacy) | Core policy | Legacy consumers | `true` | `1` | Implemented |

## Bootstrap/Discovery Family

Canonical bootstrap topic:
- `synthia/bootstrap/core`

Contract:
- Payload model: `MqttBootstrapAnnouncement` (`backend/app/system/mqtt/integration_models.py`)
- Retained: `true`
- QoS: `1`
- Publisher owner: Core embedded startup reconcile (`startup_reconcile.py`)
- Allowed anonymous access:
  - subscribe only to exact bootstrap topic
  - no publish
  - no wildcard subscribe

## Reserved-Family Access Rules (Phase 1)

- Synthia principals (`synthia_addon`, `synthia_node`) may access reserved topics only with explicit Core approval.
- Generic users cannot access reserved families by default.
- Anonymous clients are limited to bootstrap-only subscribe.

## Not Developed

- Node topic family runtime usage (`synthia/nodes/<node_id>/...`).
- Additional Core operational topic subtrees:
  - `synthia/core/status/...`
  - `synthia/core/health/...`
  - `synthia/core/events/...`
- Additional service visibility topic set beyond `synthia/services/+/catalog`.
