# Node Provider Intelligence Contract

Status: Implemented
Last Updated: 2026-03-19 17:35

## Purpose

This document defines the implemented Core-owned contract for:

- trusted-node provider intelligence ingestion
- Core persistence of provider/model routing metadata
- admin inspection of stored provider/model routing metadata

This is the canonical contract for `POST /api/system/nodes/providers/capabilities/report`
and `GET /api/system/nodes/providers/routing-metadata`.

## Current Implementation Boundary

Core currently validates, normalizes, stores, and exposes:

- provider id
- model id
- normalized model id
- pricing metrics
- latency metrics
- node availability
- source metadata
- update timestamp

Core does not currently define or expose a normative ingestion contract for these fields in this API:

- `success_rate`
- `request_count`
- `failure_count`
- usage totals
- cost totals
- percentile metrics outside the submitted `latency_metrics` map

If a node needs those fields for future routing or admin UX, that is a Core contract expansion rather than already-implemented behavior.

## Ingestion Endpoint

- Route: `POST /api/system/nodes/providers/capabilities/report`
- Auth: trusted node token via `X-Node-Trust-Token`

### Request Body

```json
{
  "node_id": "node-abc123",
  "provider_intelligence": [
    {
      "provider": "openai",
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
          }
        }
      ]
    }
  ],
  "node_available": true,
  "observed_at": "2026-03-19T17:35:00Z"
}
```

### Required Fields

- `node_id`: string
- `provider_intelligence`: array

### Optional Fields

- `node_available`: boolean
  Default: `true`
- `observed_at`: string timestamp
  Current behavior: echoed back if provided, but not used for routing-metadata persistence

## Provider Intelligence Schema

Each `provider_intelligence[]` item must be:

- `provider`: string
- `available_models`: array

Provider validation rules:

- provider id is normalized to lowercase
- provider id must match `^[a-z0-9][a-z0-9._-]{1,127}$`

Each `available_models[]` item must be:

- `model_id`: non-empty string
- `pricing`: object of numeric metric values
- `latency_metrics`: object of numeric metric values

Model validation and normalization rules:

- `model_id` must be non-empty after trimming
- `normalized_model_id` is derived by lowercasing the trimmed `model_id`
- `pricing` keys are normalized to lowercase
- `latency_metrics` keys are normalized to lowercase
- numeric values in `pricing` and `latency_metrics` must be valid floats greater than or equal to `0`
- `available_models` must be an array when present
- `pricing` and `latency_metrics` must be JSON objects when present

## Normative Metrics Shape

The exact implemented metrics contract for this ingestion API is:

- `pricing`: `map[string, non_negative_float]`
- `latency_metrics`: `map[string, non_negative_float]`

Supported keys are intentionally open-ended today. Core preserves validated numeric keys rather than enforcing a fixed enum.

Examples of keys already used in code/tests:

- `pricing.input_per_1k`
- `pricing.output_per_1k`
- `latency_metrics.p50_ms`
- `latency_metrics.p95_ms`

Important constraint:

- Metrics such as `avg_latency`, `p95_latency`, `success_rate`, `request_count`, `failure_count`, usage totals, and cost totals are not currently separate top-level normative fields in this contract.
- If a node submits those values today, the only implemented standards path is to place them inside the validated numeric maps when appropriate.
- Core routing-metadata storage currently persists only `pricing` and `latency_metrics` from this ingestion path.

## Success Response

```json
{
  "ok": true,
  "node_id": "node-abc123",
  "associated_node_id": "node-abc123",
  "provider_intelligence": [
    {
      "provider": "openai",
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
  "observed_at": "2026-03-19T17:35:00Z"
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

## Admin Read Endpoint

- Route: `GET /api/system/nodes/providers/routing-metadata`
- Auth: admin session/token
- Filters:
  - `node_id`
  - `provider`

### Response Shape

```json
{
  "ok": true,
  "items": [
    {
      "schema_version": "1",
      "node_id": "node-abc123",
      "provider": "openai",
      "model_id": "gpt-4o-mini",
      "normalized_model_id": "gpt-4o-mini",
      "pricing": {
        "input_per_1k": 0.00015,
        "output_per_1k": 0.0006
      },
      "latency_metrics": {
        "p50_ms": 120.0,
        "p95_ms": 280.0
      },
      "node_available": true,
      "source": "provider_capability_report",
      "updated_at": "2026-03-19T17:35:00+00:00"
    }
  ],
  "nodes": [
    {
      "node_id": "node-abc123",
      "node_available": true,
      "providers": [
        {
          "provider": "openai",
          "models": [
            {
              "schema_version": "1",
              "node_id": "node-abc123",
              "provider": "openai",
              "model_id": "gpt-4o-mini",
              "normalized_model_id": "gpt-4o-mini",
              "pricing": {
                "input_per_1k": 0.00015,
                "output_per_1k": 0.0006
              },
              "latency_metrics": {
                "p50_ms": 120.0,
                "p95_ms": 280.0
              },
              "node_available": true,
              "source": "provider_capability_report",
              "updated_at": "2026-03-19T17:35:00+00:00"
            }
          ]
        }
      ]
    }
  ]
}
```

## What The Admin View Proves Today

This endpoint is the best implemented Core-side evidence that a node's provider/model metadata was stored.

It currently proves storage and exposure of:

- provider/model identity
- pricing maps
- latency metric maps
- node availability
- source and update timestamp

It does not currently prove Core-side storage of:

- aggregate success/failure counts
- request totals
- usage totals
- cost totals

## Code Anchors

- `backend/app/api/system.py`
- `backend/app/system/onboarding/provider_capability_normalization.py`
- `backend/app/system/onboarding/model_routing_registry.py`

## See Also

- [API Reference](./api-reference.md)
- [Node Phase 2 Lifecycle Contract](../../nodes/node-phase2-lifecycle-contract.md)
