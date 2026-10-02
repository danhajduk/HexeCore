# Family Identity and Authorization Contract

Status: **Documented but not implemented**

The accepted cross-project contract is
`HexeCoordination/contracts/accepted/family-identity-authorization-v1.md`
(`hexe.family-identity-authorization.v1`). It defines the future Core-owned
household, person/member, guardian, consent, room, device-association, and
family-memory authorization boundary used by trusted AI nodes.

## Current compatibility boundary

Current Core behavior remains user-centric:

- `user_id` is the authenticated security principal and continues to own
  sessions, enrolled devices, conversations, and existing API records.
- The implemented platform roles remain `owner`, `admin`, `member`, and
  `guest`.
- No `person_id`, `household_id`, guardian, consent, or family-memory
  authorization store/API is implemented by Task 1013.
- Existing web-app, notification gateway, and Core-to-provider contracts are
  unchanged.

Future implementation introduces `person_id` additively. A person represents a
real household member and may exist without login credentials. A user account
may link to one person, but authentication tokens continue to use `user_id` as
their subject. Private family memory remains unavailable when the trusted Core
authorization context is missing, expired, uncertain, or denied.

## Implementation follow-up

Separate tasks are required for Core persistence/migrations, management APIs,
Settings/People UI, user-person linking, consent and guardian workflows,
Core-to-node authorization issuance, AI Node enforcement, lifecycle receipts,
and contract tests. Those tasks must preserve the accepted contract and the
existing user/session/device security boundary.
