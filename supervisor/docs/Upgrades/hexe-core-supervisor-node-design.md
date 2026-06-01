# Hexe Architecture Design Change

## Core / Supervisor / Node Model

Version: Draft Date: 2026-03-15

------------------------------------------------------------------------

# 1. Overview

This document describes the architectural change for the Hexe
ecosystem discussed in planning sessions.

The main goals of the redesign are:

-   Simplify the addon architecture
-   Standardize all external compute components as **Nodes**
-   Introduce a **Host Supervisor** responsible for local resource
    management
-   Keep **Core** focused purely on governance and orchestration

This separation improves scalability, reliability, and long‑term
maintainability of the Hexe platform.

------------------------------------------------------------------------

# 2. High Level Architecture

The ecosystem now consists of three primary layers:

Core → Supervisor → Nodes

Core acts as the control plane. Supervisors manage host resources. Nodes
provide compute or functionality.

Example topology:

Core Host └─ Supervisor ├─ AI Node ├─ Vision Node └─ Other nodes

Remote Host └─ Supervisor ├─ Edge Node └─ Voice Node

------------------------------------------------------------------------

# 3. Core Responsibilities

Core is the **governance and orchestration layer**.

Core responsibilities include:

• Node onboarding\
• Trust management\
• Policy enforcement\
• Capability registry\
• Node lifecycle orchestration\
• System configuration\
• UI and management APIs\
• Telemetry aggregation\
• Addon hosting (embedded addons only)

Core should **not run heavy compute workloads**.

Heavy tasks must be delegated to nodes.

Typical services running on Core:

-   API backend (FastAPI)
-   Web UI
-   Database
-   MQTT broker (or connection to one)
-   Scheduler
-   Governance services
-   Embedded addons

------------------------------------------------------------------------

# 4. Supervisor

Each host runs **one Supervisor**.

Supervisor responsibilities:

• Monitor local resources\
• Register nodes running on the host\
• Provide host telemetry\
• Control node lifecycle\
• Enforce local resource policies\
• Provide a host API

Supervisor acts as the **local resource authority** for the host.

Example responsibilities:

CPU monitoring\
Memory monitoring\
Process management\
Container management\
Node restart policies\
Local resource quotas

------------------------------------------------------------------------

## 5. Supervisor API

Each supervisor exposes a local control API.

Preferred transport:
- Unix domain socket: `unix:///run/hexe/supervisor.sock`

Optional fallback transport:
- Loopback-only HTTP: `http://127.0.0.1:8765/api`

The supervisor API must never bind to external interfaces by default.

Typical endpoints:

- `/api/health`
- `/api/host/info`
- `/api/resources`
- `/api/runtimes`
- `/api/runtimes/register`
- `/api/runtimes/start`
- `/api/runtimes/stop`
- `/api/runtimes/restart`
- `/api/runtimes/heartbeat`

This API allows:
- local runtimes to register with the supervisor
- local runtimes to publish heartbeats and status
- local management tools to inspect and control workloads
- host-local resource and health inspection
------------------------------------------------------------------------

# 6. Node Model

Anything that runs outside Core becomes a **Node**.

Examples:

AI Node\
Vision Node\
Voice Node\
Worker Node\
Edge Node

Nodes provide capabilities and declare them to Core.

Example capability categories:

reasoning\
vision\
image_generation\
audio_input\
audio_output\
tool_calling\
structured_output\
coding_strength

Nodes communicate with Core via:

Core API\
MQTT\
Supervisor API

------------------------------------------------------------------------

# 7. Node Startup Flow

Typical node startup sequence:

1.  Node starts
2.  Node detects host supervisor
3.  Node registers with supervisor
4.  Node begins onboarding with Core
5.  Core evaluates capabilities
6.  Node receives trust activation
7.  Node becomes operational

Supervisor acts as the **local coordination point**.

------------------------------------------------------------------------

# 8. Installation Flow

Recommended node installation flow:

1.  Node installation begins
2.  Node checks for local Supervisor
3.  If Supervisor missing:
    -   prompt user to install
    -   download supervisor package
    -   install and start supervisor
4.  Node registers with Supervisor
5.  Node begins Core onboarding

This guarantees every node runs under supervision.

------------------------------------------------------------------------

# 9. Host Telemetry

Supervisors emit host telemetry including:

CPU usage\
Memory usage\
Disk usage\
Network state\
Node health

Telemetry is sent to Core via MQTT or API.

------------------------------------------------------------------------

# 10. Hardware Strategy

Core host requirements:

CPU: 4 cores\
RAM: 8--16 GB\
Storage: SSD or NVMe\
Network: Wired Ethernet

Recommended low-cost hardware:

Used enterprise micro PC

Example:

HP EliteDesk Mini\
Intel i5‑6500T\
16GB RAM\
1TB SSD

Power consumption: \~10W idle

This makes Core inexpensive and reliable.

------------------------------------------------------------------------

# 11. Future Extensions

Possible future improvements:

• Multi‑Supervisor federation\
• Node scheduling policies\
• Resource quotas per node\
• Node marketplace\
• Supervisor cluster awareness

------------------------------------------------------------------------

# 12. Summary

The architecture now follows a clear hierarchy:

Core → governance and orchestration

Supervisor → host resource management

Nodes → compute and functionality

This model enables:

-   horizontal scalability
-   strong resource control
-   clean separation of responsibilities
-   easier future expansion of the Hexe ecosystem
