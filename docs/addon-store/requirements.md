# Addon Store Product Requirements (Phase 1)

Date: 2026-02-28
Status: Phase 1 foundation requirements

## Scope
This document defines product requirements for the official Synthia addon store foundation. Phase 1 is security-first backend scaffolding and documentation; it does not include billing, reviews, or publisher portal UX.

## Roles
- `admin`: Full control over store policy, trusted keys, approval state, and install/update/uninstall operations.
- `operator`: Day-2 operations role for installs, updates, rollbacks, and incident handling without full policy authority.
- `publisher`: Produces addon packages and release metadata; cannot force install into core without approval path.
- `org-restricted`: Consumer context where installable addons are constrained by organization policy allowlists/denylists.

## Install Flow
1. User or automation requests install of an addon release.
2. Core fetches/loads package artifact and release manifest.
3. Core validates checksum and digital signature before unpack.
4. Core validates compatibility (core version, dependencies, conflicts, permissions).
5. Core performs atomic install into addon directory with rollback guard.
6. Core records structured audit log for success/failure.
7. Addon remains disabled until all verification gates pass.

## Trust Model
- Core is the trust anchor for install decisions.
- Publisher identity is verified through public-key signature trust.
- Every release must include signed metadata + artifact checksum.
- Verification is fail-closed: invalid or missing signature/checksum blocks install.
- Policy and role checks must run before enabling installed addons.

## Billing Scope (Stub)
- Billing is out of scope for Phase 1 implementation.
- Requirements for future phases:
- Support free and paid addon metadata flags.
- Add entitlement validation hook in install/update path.
- Preserve auditability for license/entitlement decisions.

## Security Assumptions
- Core host is already access-controlled and monitored.
- Admin credentials are managed outside this spec (existing auth baseline).
- Unknown/undeclared permissions are denied by default.
- No install bypass flags are allowed in production path.
- All install/update/uninstall failures must be captured in audit logs.

## Offline Install Considerations
- Support air-gapped installs from local signed package files.
- Signature verification must work without online dependency.
- Catalog sync can be optional; install path must not require internet at execution time.
- Operator must be able to pre-stage trusted keys and package bundles.

## Future Marketplace Model
- Central catalog service with discovery, categories, and publisher metadata.
- Approval workflow before org-wide availability.
- Entitlements, billing, and compliance checks as pluggable policy hooks.
- Ratings/reviews and abuse reporting added only after trust + security baseline is stable.

