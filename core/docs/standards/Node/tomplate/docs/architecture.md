# Architecture

This node template is structured as a modular Hexe node:

- `config/` for typed configuration
- `runtime/` for orchestration
- `onboarding/` for onboarding state and flow
- `trust/` for trust state
- `core/` for Core client boundaries
- `capabilities/` for capability state
- `governance/` for readiness and governance state
- `providers/` for provider-specific behavior
- `persistence/` for stores
- `diagnostics/` for logging helpers
- `security/` for masking and redaction
