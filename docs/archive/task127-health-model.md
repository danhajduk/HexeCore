# Archived Document

Status: Outdated
Replaced by: docs/document-index.md (canonical set)
Preserved for historical reference only.

# Task 127.2: Home Full-Stack Health Model

Date: 2026-03-07

## Purpose

Define a compact Home dashboard model that separates:
- health state
- connectivity state
- sampled metrics

This model is intentionally dashboard-oriented and not a deep observability schema.

## Model Shape (Contract)

```json
{
  "status": {
    "overall": "ok|degraded|attention|unknown",
    "reasons": ["string"],
    "updated_at": "ISO-8601"
  },
  "subsystems": {
    "core": { "state": "healthy|unhealthy|unknown" },
    "supervisor": { "state": "healthy|unhealthy|unknown" },
    "mqtt": {
      "state": "connected|disconnected|unknown",
      "last_message_at": "ISO-8601|null"
    },
    "scheduler": {
      "state": "running|idle|degraded|unknown",
      "active_leases": 0,
      "queued_jobs": 0
    },
    "workers": {
      "state": "active|idle|unknown",
      "active_count": 0
    },
    "addons": {
      "state": "healthy|degraded|unknown",
      "installed_count": 0,
      "unhealthy_count": 0
    }
  },
  "connectivity": {
    "network": {
      "state": "reachable|unreachable|unknown|unavailable|not_configured"
    },
    "internet": {
      "state": "reachable|unreachable|degraded|unknown|unavailable|not_configured"
    }
  },
  "samples": {
    "internet_speed": {
      "state": "ok|unavailable|not_configured|unknown",
      "download_mbps": 0,
      "upload_mbps": 0,
      "latency_ms": 0,
      "sampled_at": "ISO-8601|null",
      "age_s": 0
    }
  }
}
```

## Missing-Data Semantics

Use these values consistently:
- `unknown`: data source exists but current value cannot be determined
- `unavailable`: capability/source is temporarily unavailable (error/timeout/failure)
- `not_configured`: capability is intentionally not configured/enabled

## Field Mapping to Current Backend Data

Mapped now (already available):
- `subsystems.core.state` <- `GET /api/health`
- `subsystems.supervisor.state` <- `GET /api/system/stats/current` (`services.supervisor.running`)
- `subsystems.mqtt.*` <- `GET /api/system/mqtt/status`
- `subsystems.scheduler.active_leases` <- `GET /api/system/scheduler/status` (`snapshot.active_leases`)
- `subsystems.scheduler.queued_jobs` <- sum of `snapshot.queue_depths`
- `subsystems.workers.active_count` <- scheduler `active_leases`
- `subsystems.addons.*` <- `GET /api/addons`

Not yet available (requires lightweight backend extension in later subtasks):
- `connectivity.network.state`
- `connectivity.internet.state`
- `samples.internet_speed.*`

## Derived-State Rules (For Home)

Overall status precedence:
1. `attention` if core unavailable or supervisor unhealthy
2. `degraded` if MQTT disconnected, scheduler degraded, internet unreachable/degraded, or unhealthy addons > 0
3. `ok` if critical subsystems are healthy/connected and no degraded triggers
4. `unknown` if required signals are missing

Reason strings should be short and user-facing, for example:
- `MQTT disconnected`
- `Scheduler unavailable`
- `Internet unreachable`
- `No workers active`

## Implementation Boundary for 127.2

This step defines the contract only.
No UI rendering changes, endpoint additions, or speed checks are implemented in this subtask.
