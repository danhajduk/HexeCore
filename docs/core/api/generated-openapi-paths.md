# Generated OpenAPI Paths

Status: Generated

This file is generated from `openapi-paths.snapshot.json`.
Do not edit path rows by hand; run `python tools/update_api_route_appendix.py --write`.

Path count: 243

| Path | Methods |
| --- | --- |
| `/api/addons` | `GET` |
| `/api/addons/errors` | `GET` |
| `/api/addons/install/start` | `POST` |
| `/api/addons/install/{session_id}` | `GET` |
| `/api/addons/install/{session_id}/configure` | `POST` |
| `/api/addons/install/{session_id}/deployment/select` | `POST` |
| `/api/addons/install/{session_id}/permissions/approve` | `POST` |
| `/api/addons/install/{session_id}/verify` | `POST` |
| `/api/addons/mqtt` | `GET` |
| `/api/addons/mqtt/api/addon/capabilities` | `GET` |
| `/api/addons/mqtt/api/addon/config` | `POST` |
| `/api/addons/mqtt/api/addon/config/effective` | `GET` |
| `/api/addons/mqtt/api/addon/health` | `GET` |
| `/api/addons/mqtt/api/addon/meta` | `GET` |
| `/api/addons/mqtt/topics` | `GET` |
| `/api/addons/mqtt/users` | `GET` |
| `/api/addons/mqtt/{path}` | `GET` |
| `/api/addons/registry` | `GET` |
| `/api/addons/registry/{addon_id}` | `GET` |
| `/api/addons/registry/{addon_id}/configure` | `POST` |
| `/api/addons/registry/{addon_id}/register` | `POST` |
| `/api/addons/registry/{addon_id}/verify` | `POST` |
| `/api/addons/{addon_id}/enable` | `POST` |
| `/api/admin/addons/registry` | `GET, POST` |
| `/api/admin/addons/registry/{addon_id}` | `DELETE` |
| `/api/admin/reload` | `POST` |
| `/api/admin/reload/status` | `GET` |
| `/api/admin/session/login` | `POST` |
| `/api/admin/session/login-user` | `POST` |
| `/api/admin/session/logout` | `POST` |
| `/api/admin/session/status` | `GET` |
| `/api/admin/users` | `GET, POST` |
| `/api/admin/users/{username}` | `DELETE` |
| `/api/architecture` | `GET` |
| `/api/auth/service-token` | `POST` |
| `/api/auth/service-token/rotate` | `POST` |
| `/api/edge/cloudflare` | `GET` |
| `/api/edge/cloudflare/provision` | `POST` |
| `/api/edge/cloudflare/settings` | `GET, PUT` |
| `/api/edge/cloudflare/test` | `POST` |
| `/api/edge/public-identity` | `GET` |
| `/api/edge/publications` | `GET, POST` |
| `/api/edge/publications/{publication_id}` | `DELETE, PATCH` |
| `/api/edge/reconcile` | `POST` |
| `/api/edge/status` | `GET` |
| `/api/health` | `GET` |
| `/api/nodes` | `GET` |
| `/api/nodes/{node_id}` | `GET` |
| `/api/nodes/{node_id}/ui-manifest` | `GET` |
| `/api/policy/grants` | `GET, POST` |
| `/api/policy/revocations` | `GET, POST` |
| `/api/services/register` | `POST` |
| `/api/services/resolve` | `GET` |
| `/api/store/admin/audit` | `GET` |
| `/api/store/catalog` | `GET` |
| `/api/store/install` | `POST` |
| `/api/store/schema` | `GET` |
| `/api/store/sources` | `GET, POST` |
| `/api/store/sources/{source_id}` | `DELETE` |
| `/api/store/sources/{source_id}/refresh` | `POST` |
| `/api/store/sources/{source_id}/validate` | `GET` |
| `/api/store/standalone/update` | `POST` |
| `/api/store/status/summary` | `GET` |
| `/api/store/status/{addon_id}` | `GET` |
| `/api/store/status/{addon_id}/diagnostics` | `GET` |
| `/api/store/uninstall` | `POST` |
| `/api/store/update` | `POST` |
| `/api/system-stats/current` | `GET` |
| `/api/system-stats/health` | `GET` |
| `/api/system-stats/history` | `GET` |
| `/api/system/addons/runtime` | `GET` |
| `/api/system/addons/runtime/{addon_id}` | `GET` |
| `/api/system/debug/publish` | `POST` |
| `/api/system/debug/subscribe` | `POST` |
| `/api/system/debug/subscribe/{subscription_id}/messages` | `GET` |
| `/api/system/debug/unsubscribe` | `POST` |
| `/api/system/events` | `GET` |
| `/api/system/hardware/access-requests` | `GET` |
| `/api/system/hardware/access-requests/{request_id}/decision` | `POST` |
| `/api/system/hardware/bluetooth/ble/pairing-sessions` | `GET, POST` |
| `/api/system/hardware/bluetooth/ble/pairing-sessions/{session_id}` | `GET` |
| `/api/system/hardware/bluetooth/ble/pairing-sessions/{session_id}/approve` | `POST` |
| `/api/system/hardware/bluetooth/ble/pairing-sessions/{session_id}/cancel` | `POST` |
| `/api/system/hardware/leases/validate` | `POST` |
| `/api/system/mqtt/audit` | `GET` |
| `/api/system/mqtt/bootstrap/publish` | `POST` |
| `/api/system/mqtt/debug/acl` | `GET` |
| `/api/system/mqtt/debug/authority` | `GET` |
| `/api/system/mqtt/debug/config` | `GET` |
| `/api/system/mqtt/debug/effective-access-normalized/{principal_id}` | `GET` |
| `/api/system/mqtt/debug/effective-access/{principal_id}` | `GET` |
| `/api/system/mqtt/debug/notifications/test-flow` | `POST` |
| `/api/system/mqtt/debug/topic-validate` | `POST` |
| `/api/system/mqtt/generic-users` | `POST` |
| `/api/system/mqtt/generic-users/{principal_id}/effective-access` | `GET` |
| `/api/system/mqtt/generic-users/{principal_id}/grants` | `PATCH` |
| `/api/system/mqtt/generic-users/{principal_id}/revoke` | `POST` |
| `/api/system/mqtt/generic-users/{principal_id}/rotate-credentials` | `POST` |
| `/api/system/mqtt/grants` | `GET` |
| `/api/system/mqtt/grants/{addon_id}` | `GET` |
| `/api/system/mqtt/health` | `GET` |
| `/api/system/mqtt/node-bridge-grants` | `GET` |
| `/api/system/mqtt/node-bridge-grants/request` | `POST` |
| `/api/system/mqtt/node-bridge-grants/{grant_id}` | `GET` |
| `/api/system/mqtt/node-bridge-grants/{grant_id}/approve` | `POST` |
| `/api/system/mqtt/node-bridge-grants/{grant_id}/credential/claim` | `POST` |
| `/api/system/mqtt/node-bridge-grants/{grant_id}/provision` | `POST` |
| `/api/system/mqtt/node-bridge-grants/{grant_id}/revoke` | `POST` |
| `/api/system/mqtt/node-domain-events/decisions` | `GET` |
| `/api/system/mqtt/noisy-clients` | `GET` |
| `/api/system/mqtt/noisy-clients/{principal_id}/actions/{action}` | `POST` |
| `/api/system/mqtt/observability` | `GET` |
| `/api/system/mqtt/principals` | `GET` |
| `/api/system/mqtt/principals/{principal_id}` | `DELETE, GET` |
| `/api/system/mqtt/principals/{principal_id}/actions/{action}` | `POST` |
| `/api/system/mqtt/principals/{principal_id}/activate` | `POST` |
| `/api/system/mqtt/principals/{principal_id}/disable` | `POST` |
| `/api/system/mqtt/principals/{principal_id}/last-seen` | `GET` |
| `/api/system/mqtt/principals/{principal_id}/permissions` | `GET` |
| `/api/system/mqtt/principals/{principal_id}/revoke` | `POST` |
| `/api/system/mqtt/principals/{principal_id}/rotate-password` | `POST` |
| `/api/system/mqtt/registrations/approve` | `POST` |
| `/api/system/mqtt/registrations/{addon_id}/provision` | `POST` |
| `/api/system/mqtt/registrations/{addon_id}/revoke` | `POST` |
| `/api/system/mqtt/reload` | `POST` |
| `/api/system/mqtt/restart` | `POST` |
| `/api/system/mqtt/runtime/config` | `GET` |
| `/api/system/mqtt/runtime/health` | `GET` |
| `/api/system/mqtt/runtime/init` | `POST` |
| `/api/system/mqtt/runtime/rebuild` | `POST` |
| `/api/system/mqtt/runtime/sessions` | `GET` |
| `/api/system/mqtt/runtime/start` | `POST` |
| `/api/system/mqtt/runtime/stats/history` | `GET` |
| `/api/system/mqtt/runtime/stop` | `POST` |
| `/api/system/mqtt/runtime/topics` | `GET` |
| `/api/system/mqtt/setup-state` | `POST` |
| `/api/system/mqtt/setup-summary` | `GET` |
| `/api/system/mqtt/setup/apply` | `POST` |
| `/api/system/mqtt/setup/test-connection` | `POST` |
| `/api/system/mqtt/status` | `GET` |
| `/api/system/mqtt/test` | `POST` |
| `/api/system/mqtt/users` | `POST` |
| `/api/system/mqtt/users/export` | `GET` |
| `/api/system/mqtt/users/import` | `POST` |
| `/api/system/mqtt/users/{principal_id}` | `DELETE, PATCH` |
| `/api/system/mqtt/users/{principal_id}/rotate` | `POST` |
| `/api/system/nodes/budgets` | `GET` |
| `/api/system/nodes/budgets/declaration` | `POST` |
| `/api/system/nodes/budgets/export` | `GET` |
| `/api/system/nodes/budgets/policy/current` | `GET` |
| `/api/system/nodes/budgets/policy/refresh` | `POST` |
| `/api/system/nodes/budgets/usage-summary` | `POST` |
| `/api/system/nodes/budgets/{node_id}` | `DELETE, GET, PUT` |
| `/api/system/nodes/budgets/{node_id}/customers` | `GET` |
| `/api/system/nodes/budgets/{node_id}/customers/{customer_id}` | `DELETE, PUT` |
| `/api/system/nodes/budgets/{node_id}/override` | `POST` |
| `/api/system/nodes/budgets/{node_id}/providers` | `GET` |
| `/api/system/nodes/budgets/{node_id}/providers/{provider_id}` | `DELETE, PUT` |
| `/api/system/nodes/budgets/{node_id}/reset` | `POST` |
| `/api/system/nodes/budgets/{node_id}/top-up` | `POST` |
| `/api/system/nodes/budgets/{node_id}/usage` | `GET` |
| `/api/system/nodes/budgets/{node_id}/usage-reports` | `GET` |
| `/api/system/nodes/capabilities/declaration` | `POST` |
| `/api/system/nodes/capabilities/profiles` | `GET` |
| `/api/system/nodes/capabilities/profiles/{profile_id}` | `GET` |
| `/api/system/nodes/governance/current` | `GET` |
| `/api/system/nodes/governance/refresh` | `POST` |
| `/api/system/nodes/hardware/access-requests` | `POST` |
| `/api/system/nodes/hardware/access-requests/schema` | `GET` |
| `/api/system/nodes/hardware/ble/provisioning/schemas/{node_profile_id}` | `GET` |
| `/api/system/nodes/hardware/bluetooth/ble/identity` | `POST` |
| `/api/system/nodes/hardware/bluetooth/ble/pairing-sessions` | `POST` |
| `/api/system/nodes/hardware/bluetooth/ble/pairing-sessions/{session_id}` | `GET` |
| `/api/system/nodes/hardware/bluetooth/ble/pairing-sessions/{session_id}/approve` | `POST` |
| `/api/system/nodes/hardware/bluetooth/ble/pairing-sessions/{session_id}/cancel` | `POST` |
| `/api/system/nodes/hardware/bluetooth/ble/scan` | `POST` |
| `/api/system/nodes/hardware/leases/{lease_id}/release` | `POST` |
| `/api/system/nodes/onboarding/sessions` | `GET, POST` |
| `/api/system/nodes/onboarding/sessions/cancel-active` | `POST` |
| `/api/system/nodes/onboarding/sessions/{session_id}` | `GET` |
| `/api/system/nodes/onboarding/sessions/{session_id}/approve` | `POST` |
| `/api/system/nodes/onboarding/sessions/{session_id}/finalize` | `GET` |
| `/api/system/nodes/onboarding/sessions/{session_id}/reject` | `POST` |
| `/api/system/nodes/operational-status/{node_id}` | `GET` |
| `/api/system/nodes/providers/capabilities/report` | `POST` |
| `/api/system/nodes/providers/model-policy` | `GET` |
| `/api/system/nodes/providers/model-policy/{provider}` | `DELETE, PUT` |
| `/api/system/nodes/providers/routing-metadata` | `GET` |
| `/api/system/nodes/reauth/sessions` | `POST` |
| `/api/system/nodes/reauth/sessions/{session_id}` | `GET` |
| `/api/system/nodes/reauth/sessions/{session_id}/approve` | `POST` |
| `/api/system/nodes/reauth/sessions/{session_id}/finalize` | `GET` |
| `/api/system/nodes/reauth/sessions/{session_id}/reject` | `POST` |
| `/api/system/nodes/registrations` | `GET` |
| `/api/system/nodes/registrations/{node_id}` | `DELETE, GET` |
| `/api/system/nodes/registrations/{node_id}/metadata` | `PUT` |
| `/api/system/nodes/registrations/{node_id}/revoke` | `POST` |
| `/api/system/nodes/registry` | `GET` |
| `/api/system/nodes/services/authorize` | `POST` |
| `/api/system/nodes/services/resolve` | `POST` |
| `/api/system/nodes/telemetry` | `POST` |
| `/api/system/nodes/trust-status/{node_id}` | `GET` |
| `/api/system/nodes/{node_id}/hardware/access-requests` | `GET` |
| `/api/system/platform` | `GET` |
| `/api/system/principals/{principal_id}` | `DELETE, GET` |
| `/api/system/principals/{principal_id}/activate` | `POST` |
| `/api/system/principals/{principal_id}/disable` | `POST` |
| `/api/system/principals/{principal_id}/last_seen` | `GET` |
| `/api/system/principals/{principal_id}/permissions` | `GET` |
| `/api/system/principals/{principal_id}/revoke` | `POST` |
| `/api/system/principals/{principal_id}/rotate_password` | `POST` |
| `/api/system/repo/status` | `GET` |
| `/api/system/runtime/block` | `POST` |
| `/api/system/runtime/config` | `GET` |
| `/api/system/runtime/disconnect` | `POST` |
| `/api/system/runtime/health` | `GET` |
| `/api/system/runtime/sessions` | `GET` |
| `/api/system/runtime/stats/history` | `GET` |
| `/api/system/runtime/throttle` | `POST` |
| `/api/system/runtime/topics` | `GET` |
| `/api/system/scheduler/internal` | `GET` |
| `/api/system/settings` | `GET` |
| `/api/system/settings/{key}` | `GET, PUT` |
| `/api/system/stack/summary` | `GET` |
| `/api/system/stats/current` | `GET` |
| `/api/system/supervisor/core/runtimes/{runtime_id}/resources/history` | `GET` |
| `/api/system/supervisor/resources/history` | `GET` |
| `/api/system/supervisor/runtimes/{node_id}/resources/history` | `GET` |
| `/api/system/supervisor/summary` | `GET` |
| `/api/system/supervisors` | `GET` |
| `/api/system/supervisors/enroll` | `POST` |
| `/api/system/supervisors/enrollment-tokens` | `POST` |
| `/api/system/supervisors/heartbeat` | `POST` |
| `/api/system/supervisors/local/core-runtimes` | `POST` |
| `/api/system/supervisors/register` | `POST` |
| `/api/system/supervisors/{supervisor_id}` | `DELETE, GET` |
| `/api/system/supervisors/{supervisor_id}/core/runtimes/{runtime_id}/resources/history` | `GET` |
| `/api/system/supervisors/{supervisor_id}/resources/history` | `GET` |
| `/api/system/supervisors/{supervisor_id}/runtimes/{node_id}/resources/history` | `GET` |
| `/api/system/supervisors/{supervisor_id}/update/start` | `POST` |
| `/api/system/supervisors/{supervisor_id}/update/status` | `GET` |
| `/api/telemetry/usage` | `GET, POST` |
| `/api/telemetry/usage/stats` | `GET` |
