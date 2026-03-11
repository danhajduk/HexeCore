# Archived Document

Status: Outdated
Replaced by: docs/document-index.md (canonical set)
Preserved for historical reference only.

# Synthia MQTT Addon — Architecture Blueprint

## Overview

The **Synthia MQTT Addon** provides the governed messaging gateway and broker authority for the Synthia platform.

It enables:
- internal event bus communication
- addon lifecycle visibility
- telemetry distribution
- inter-addon messaging
- optional Home Assistant MQTT integration
- managed MQTT access for addons

The addon supports both:
- **direct MQTT clients**
- **API gateway publishing**

while maintaining centralized governance of broker access and topic permissions.

## Core Principles

1. MQTT is used primarily for **internal Synthia communication**, not just Home Assistant integration.
2. The platform supports a **hybrid transport model**:
   - addons may use direct MQTT
   - addons may publish via the MQTT addon API
   - direct MQTT is **not required**
3. MQTT access is **governed**:
   - addons must **register for MQTT access**
   - Core approves access
   - MQTT addon provisions credentials and ACLs
4. Platform services prefer **API over MQTT** for control-plane operations.
5. MQTT remains the **event distribution layer** for the platform.

## High-Level Architecture

```text
              ┌─────────────┐
              │    Core     │
              └──────┬──────┘
                     │ API
                     ▼
              ┌─────────────┐
              │ MQTT Addon  │
              │ (Gateway)   │
              └──────┬──────┘
                     │
              MQTT Broker
        (built-in or external)
                     │
     ┌───────────────┼───────────────┐
     │               │               │
 Vision Addon   Scheduler Addon   Other Addons
     │               │               │
     └───────────────┴───────────────┘
             MQTT Event Bus
```

## Responsibilities

### MQTT Addon

The MQTT addon is responsible for:

#### Broker Integration
- connect to external broker
- optionally run built-in Mosquitto container
- monitor broker health

#### MQTT Registration Service
- receive MQTT access requests
- provision broker credentials
- assign topic permissions
- generate ACLs

#### Messaging Gateway
- provide API publish endpoint
- enforce topic contracts
- support HA discovery helpers

#### Governance
- enforce reserved namespaces
- validate topics
- optionally validate message schema

#### Observability
- broker health reporting
- usage metrics
- tracing/debugging tools
- topic explorer UI

## Broker Modes

The MQTT addon supports three broker configurations.

### Mode 1 — Built-in Managed Broker

The addon starts a Mosquitto container:

```text
synthia-addon-mqtt-mosquitto
```

Capabilities:
- Synthia manages users and ACLs
- full hybrid MQTT support
- automatic credential provisioning
- easiest setup option

### Mode 2 — External Broker (Gateway Mode)

Synthia connects to an existing broker using configured credentials.

Capabilities:
- gateway publishing always supported
- direct MQTT clients may be limited
- broker ACL management remains external

### Mode 3 — External Broker (Advanced Mode)

External broker with optional managed provisioning.

Capabilities:
- direct MQTT client credentials possible
- only supported for compatible broker types
- otherwise requires manual credential configuration

## Setup UI

After installation, the addon exposes a **Setup UI**.

### Setup States

```text
unconfigured
configuring
ready
error
degraded
```

### Setup Options

The UI allows configuration of:

#### Broker mode
- built-in Mosquitto
- external broker

#### External broker settings

```text
host
port
TLS enabled
username/password
optional base topic
```

#### Connection test
Before setup completes:
- connection must be validated
- broker health verified

## MQTT Registration Model

Addons must request MQTT access.

### Approval Flow

```text
Addon → Core → MQTT Addon
```

1. addon requests MQTT access
2. Core validates addon identity
3. Core approves permissions
4. MQTT addon provisions broker credentials
5. contract returned to addon

### Registration Request

```json
{
  "addon_id": "vision",
  "access_mode": "both",
  "publish_topics": [
    "synthia/addons/vision/announce",
    "synthia/addons/vision/health",
    "synthia/addons/vision/event/#",
    "synthia/addons/vision/state/#"
  ],
  "subscribe_topics": [
    "synthia/system/#",
    "synthia/addons/vision/command/#"
  ],
  "capabilities": {
    "events": true,
    "state": true,
    "commands": true,
    "ha_discovery": "gateway_managed"
  }
}
```

### Registration Result

```json
{
  "addon_id": "vision",
  "status": "approved",
  "access_mode": "both",
  "direct_mqtt": {
    "broker_host": "mqtt-addon",
    "broker_port": 1883,
    "username": "addon_vision_main",
    "password": "generated-secret"
  },
  "permissions": {
    "publish": [
      "synthia/addons/vision/event/#",
      "synthia/addons/vision/state/#"
    ],
    "subscribe": [
      "synthia/system/#",
      "synthia/addons/vision/command/#"
    ]
  }
}
```

## Topic Namespace Model

### Reserved Platform Namespaces

```text
synthia/system/...
synthia/core/...
synthia/supervisor/...
synthia/scheduler/...
synthia/policy/...
synthia/telemetry/...
```

Only platform services may publish here.

### Addon Namespaces

Each addon owns:

```text
synthia/addons/<addon_id>/...
```

Example:

```text
synthia/addons/vision/event/person_detected
```

## Standard Addon Lifecycle Topics

Every MQTT-enabled addon must support:

```text
synthia/addons/<addon_id>/announce
synthia/addons/<addon_id>/health
```

### Announce

Purpose:
- identity
- version
- capabilities

Rules:
- retained
- QoS 1
- published on startup
- republished on reconnect

### Health

Purpose:
- runtime health
- dependency status

Rules:
- retained
- QoS 1
- periodic heartbeat
- LWT for disconnect detection

## Optional Topic Families

### Events
```text
synthia/addons/<addon_id>/event/<event_name>
```

Example:
```text
synthia/addons/vision/event/person_detected
```

### State
```text
synthia/addons/<addon_id>/state/<entity>
```

### Commands
```text
synthia/addons/<addon_id>/command/<command>
```

Only available if declared during registration.

## Message Envelope Format

Platform topics use a **standard JSON envelope**.

### Required Envelope

```json
{
  "spec_version": "1.0",
  "message_type": "event",
  "source": {
    "kind": "addon",
    "id": "vision",
    "instance": "vision-main"
  },
  "timestamp": "2026-03-07T18:00:00Z",
  "message_id": "optional",
  "correlation_id": "optional",
  "payload": {}
}
```

### Payload Structure

The `payload` contains domain-specific data.

Example:

```json
{
  "payload": {
    "name": "person_detected",
    "camera": "front_door",
    "confidence": 0.91
  }
}
```

## Delivery Rules

### Retained Topics
Retained:
- announce
- health
- state
- policy
- HA discovery

### Non-Retained Topics
- event
- command
- telemetry

### QoS Defaults

| Traffic Type | QoS |
|---|---:|
| platform control | 1 |
| announce | 1 |
| health | 1 |
| state | 1 |
| events | 0 or 1 |
| telemetry | 0 |

QoS 2 is not used by default.

## Home Assistant Autodiscovery

HA support is optional.

Modes:

### Gateway Managed
MQTT addon publishes HA discovery/state.

### Direct Addon Managed
Addon may publish directly if granted permission.

This must be approved during MQTT registration.

## MQTT Addon API

Core gateway endpoints include:

```text
POST /publish
POST /register
GET /health
GET /metrics
```

Future endpoints may include:

```text
/topics
/traces
/clients
```

## Phase Implementation Plan

### Phase 1 — Core Infrastructure
1. broker management
2. MQTT registration service
3. credential provisioning
4. gateway publish API
5. broker health reporting

### Phase 2 — Governance and Observability
1. topic validation
2. schema validation
3. message tracing
4. topic explorer UI
5. HA discovery helpers
6. MQTT usage metrics

## Platform Rule

Core, Supervisor, and Scheduler should **prefer API calls** over MQTT for control-plane operations.

MQTT should be used primarily for:
- event broadcasting
- telemetry
- lifecycle signals
- asynchronous notifications

## Summary

The MQTT addon acts as the **governed messaging gateway for the Synthia platform**, enabling a hybrid event bus architecture while maintaining centralized control over broker access, topic namespaces, and messaging contracts.
