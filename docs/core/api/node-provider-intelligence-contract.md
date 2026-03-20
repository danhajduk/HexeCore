# Node Provider Intelligence Contract

Status: Implemented
Last Updated: 2026-03-20

## Purpose

Defines the current Core-owned contract for trusted-node provider intelligence ingestion, declared capacity publication, routing-metadata persistence, and admin inspection.

This is the canonical contract for:

- `POST /api/system/nodes/providers/capabilities/report`
- `GET /api/system/nodes/providers/routing-metadata`

## Current Implementation Boundary

Core currently validates, normalizes, stores, and exposes:

- provider id
- model id
- normalized model id
- pricing metrics
- latency metrics
- declared service-level capacity metadata
- declared provider-level capacity metadata
- declared model-level capacity metadata
- node availability
- source metadata
- update timestamp

Core still does not define first-class top-level routing-metadata fields for:

- `success_rate`
- `request_count`
- `failure_count`
- aggregate usage totals
- aggregate cost totals

If a node needs those values surfaced separately in admin routing views, that remains a future Core contract expansion.

## Ingestion Endpoint

- Route: `POST /api/system/nodes/providers/capabilities/report`
- Auth: trusted node token via `X-Node-Trust-Token`

### Request Body

```json
{
  "node_id": "node-abc123",
  "service_capacity": {
    "service": "ai.inference",
    "period": "daily",
    "limits": {
      "max_tokens": 1000000,
      "max_cost_cents": 2500
    },
    "concurrency": {
      "max_inflight_requests": 4
    },
    "sla_hints": {
      "availability_tier": "best_effort"
    }
  },
  "provider_intelligence": [
    {
      "provider": "openai",
      "capacity": {
        "period": "daily",
        "limits": {
          "max_tokens": 750000
        }
      },
      "available_models": [
        {
          "model_id": "gpt-4o-mini",
          "pricing": {
            "input_per_1k": 0.00015,
            "output_per_1k": 0.0006
          },
          "latency_metrics": {
            "p50_ms": 120.0,
            "p95_ms": 280.0
          },
          "capacity": {
            "period": "daily",
            "limits": {
              "max_requests": 5000
            }
          }
        }
      ]
    }
  ],
  "node_available": true,
  "observed_at": "2026-03-20T07:40:00Z"
}
```

### Required Fields

- `node_id`
- `provider_intelligence`

### Optional Fields

- `service_capacity`
- `node_available`
- `observed_at`

Current `observed_at` behavior:

- echoed back if provided
- not currently used as the persisted `updated_at` source in routing metadata

## Provider Intelligence Schema

Each `provider_intelligence[]` item must include:

- `provider`
- `available_models`

Optional provider fields:

- `capacity`

Each `available_models[]` item may include:

- `model_id`
- `pricing`
- `latency_metrics`
- `capacity`

Provider validation rules:

- provider id is normalized to lowercase
- provider id must match `^[a-z0-9][a-z0-9._-]{1,127}$`

Model validation and normalization rules:

- `model_id` must be non-empty after trimming
- `normalized_model_id` is derived by lowercasing the trimmed `model_id`
- `pricing` keys are normalized to lowercase
- `latency_metrics` keys are normalized to lowercase
- numeric values in `pricing` and `latency_metrics` must be valid floats greater than or equal to `0`

## Normative Metrics And Capacity Shape

The implemented routing-metadata schema is:

- `pricing`: `map[string, non_negative_float]`
- `latency_metrics`: `map[string, non_negative_float]`
- `service_capacity`: capacity descriptor object
- `provider_capacity`: capacity descriptor object
- `model_capacity`: capacity descriptor object

Capacity descriptor fields:

- `service` optional string
- `period` optional string
- `limits`: `map[string, non_negative_float]`
- `concurrency`: `map[string, non_negative_float]`
- `sla_hints`: shallow JSON object of scalar or scalar-list values

Common implemented capacity keys:

- `limits.max_requests`
- `limits.max_tokens`
- `limits.max_cost_cents`
- `limits.max_bytes`
- `limits.max_compute_units`
- `concurrency.max_inflight_requests`

Unknown `max_*` numeric limit keys are preserved.

## Success Response

```json
{
  "ok": true,
  "node_id": "node-abc123",
  "associated_node_id": "node-abc123",
  "service_capacity": {
    "service": "ai.inference",
    "period": "daily",
    "limits": {
      "max_tokens": 1000000,
      "max_cost_cents": 2500
    }
  },
  "provider_intelligence": [
    {
      "provider": "openai",
      "service_capacity": {
        "service": "ai.inference",
        "period": "daily",
        "limits": {
          "max_tokens": 1000000,
          "max_cost_cents": 2500
        }
      },
      "capacity": {
        "period": "daily",
        "limits": {
          "max_tokens": 750000
        }
      },
      "available_models": [
        {
          "model_id": "gpt-4o-mini",
          "normalized_model_id": "gpt-4o-mini",
          "descriptor_id": "openai:gpt-4o-mini",
          "availability": "available",
          "pricing": {
            "input_per_1k": 0.00015,
            "output_per_1k": 0.0006
          },
          "latency_metrics": {
            "p50_ms": 120.0,
            "p95_ms": 280.0
          },
          "capacity": {
            "period": "daily",
            "limits": {
              "max_requests": 5000
            }
          }
        }
      ]
    }
  ],
  "unified_model_descriptors": [
    {
      "normalized_model_id": "gpt-4o-mini",
      "model_id": "gpt-4o-mini",
      "providers": ["openai"],
      "provider_count": 1
    }
  ],
  "node_available": true,
  "observed_at": "2026-03-20T07:40:00Z"
}
```

## Error Behavior

Possible error responses include:

- `401`: missing trust token
- `403`: untrusted node or untrusted registration state
- `400`: invalid report payload

Representative `400 detail.error` values:

- `node_id_required`
- `invalid_provider_id`
- `provider_available_models_must_be_list`
- `invalid_model_id`
- `invalid_pricing_value`
- `invalid_latency_value`
- `invalid_service_capacity`
- `invalid_provider_capacity`
- `invalid_model_capacity`

## Admin Read Endpoint

- Route: `GET /api/system/nodes/providers/routing-metadata`
- Auth: admin session/token
- Filters:
  - `node_id`
  - `provider`

### Response Shape

`items[]` rows now include:

- `service_capacity`
- `provider_capacity`
- `model_capacity`

Grouped `nodes[]` output now includes:

- node-level `service_capacity`
- provider-level `capacity`
- model rows carrying the same persisted per-model capacity metadata

## Code Anchors

- `backend/app/system/onboarding/provider_capability_normalization.py`
- `backend/app/system/onboarding/model_routing_registry.py`
- `backend/app/api/system.py`

## See Also

- [API Reference](./api-reference.md)
- [Node Budget Management Contract](../../nodes/node-budget-management-contract.md)
