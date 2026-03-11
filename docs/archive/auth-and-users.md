# Archived Document

Status: Outdated
Replaced by: docs/document-index.md (canonical set)
Preserved for historical reference only.

# Authentication and Users Documentation

Last Updated: 2026-03-07 14:51 US/Pacific

## Authentication Surfaces

Admin/session authentication:
- cookie-session endpoints in `app/api/admin.py`
- login via token or username/password
- session status/logout endpoints

Service authentication:
- service token issue/rotate endpoints in `app/system/auth/router.py`
- token signing/verification in `app/system/auth/tokens.py`

## User Management

- users stored in SQLite via `app/system/users/store.py`
- CRUD endpoints in `app/system/users/router.py`
- admin user auto-seeded from env (`SYNTHIA_ADMIN_USERNAME`, `SYNTHIA_ADMIN_PASSWORD` or fallback token)

## Roles and Permission Boundaries

- admin: privileged control-plane endpoints
- service: telemetry/policy/service token workflows
- guest: read-only/public paths

## Session and Token Behavior

- admin session managed with signed cookie + server-side checks
- service tokens are JWT-like signed tokens derived from key material in settings store

## Not Developed

- Multi-factor authentication
- External identity providers (OIDC/SAML)
- Fine-grained RBAC beyond current role partitioning
