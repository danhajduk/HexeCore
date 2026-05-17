# Synthia Core / Supervisor / Nodes Architecture --- Core Structure

Last Updated: 2026-03-07 14:51 US/Pacific

Version: 0.1\
Date: 2026-02-28

## 1. Core Role: Control Plane

Synthia Core is **not** in the data path of addons.\
It acts as:

-   Addon registry
-   Authentication + authorization authority
-   Token issuer
-   Policy & quota authority
-   Reverse proxy for browser → addon calls
-   Unified UI shell
-   Global settings manager
-   Telemetry aggregator
-   MQTT authority for platform messaging, notifications, and broker policy
-   Scheduler and workload admission authority

Core must NOT: - Relay sensor events - Relay AI inference traffic - Sit
in high-frequency data paths

------------------------------------------------------------------------

## 2. Registry and External Boundary

Core maintains persistent registry state for embedded addons, compatibility-era standalone addons, and external node declarations:

-   id
-   name
-   base_url
-   capabilities (string list)
-   health status
-   last_seen
-   auth_mode

Example capabilities: - vision.ingest - ai.classify - gmail.send -
storage.object

Canonical boundary:

-   Embedded addons remain inside Core.
-   Nodes are the canonical external functionality and scheduled work boundary.
-   Compatibility-era standalone addons may still appear in the registry during migration.

------------------------------------------------------------------------

## 3. Reverse Proxy Model

Browser → Core → Addon or Node-facing service

Core proxies: - /api/addons/{id}/* - /addons/{id}/*

Addons may still expose standalone UI directly.

------------------------------------------------------------------------

## 4. MQTT Options

Core supports two install modes:

A. Local MQTT Addon\
- Runs broker locally (Mosquitto container) - Persistent storage -
Health monitoring

B. External MQTT Broker\
- Host/port/credentials provided during install - Connection test
required

MQTT remains Core-owned even when the broker is external. Core is responsible for broker configuration, internal notification topics, and platform event publication.

------------------------------------------------------------------------

## 5. External Runtime Model

External functionality may run on separate machines, but the canonical runtime categories are now split between Supervisor and Nodes.

Core responsibilities: - Service discovery - Policy distribution - Token
issuing - workload admission - UI/governance surfaces

Supervisor responsibilities: - host-local process/runtime control -
resource reporting - lifecycle actions

Node responsibilities: - external execution - external capability delivery
- node-local health/capability declaration

Core must not disturb addon runtime operation.

------------------------------------------------------------------------

## 6. Supervisor Layer

Supervisor endpoints now exist in the active platform surface:

- `GET /api/supervisor/resources`
- `GET /api/supervisor/runtime`
- `GET /api/supervisor/nodes`
- `GET /api/supervisor/admission`
- `POST /api/supervisor/nodes/{node_id}/start`
- `POST /api/supervisor/nodes/{node_id}/stop`
- `POST /api/supervisor/nodes/{node_id}/restart`

Supervisor is the host-local runtime authority. It is not the external platform boundary for new functionality; Nodes fill that role.
