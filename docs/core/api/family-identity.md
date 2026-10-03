# Family identity administration

Core implements `hexe.family-identity-authorization.v1` additively. A `user_id`
is still a login/security principal. A `person_id` is a real household member
and never contains credentials, sessions, platform roles, or biometric data.
Either record may exist without a link; v1 permits at most one active link in
each direction.

The standard local UI is `Settings → People`. Its management API is mounted at
`/api/admin/family` for local administrator sessions and at
`/api/web-app/admin/family` for owner/admin human tokens. Human-token changes
to people, links, guardian authority, consent, export, and deletion require
password step-up. `GET .../family/me` is available to an authenticated user and
returns only that user's linked person, consent, and guardian state.

Managed resources include households, people, user links, guardian authority,
purpose-specific consent, rooms, endpoint assignments, and export/deletion
lifecycle requests. Person updates require an expected version. Deletion and
export requests remain visibly `incomplete` until required node receipts are
recorded; they are not presented as completed merely because Core accepted the
request.

Core's authorization evaluator denies personal-sensitive operations for an
unlinked, wrong-household, uncertain, wrong-room, expired, or unconsented
identity. An active denial overrides a grant. Issued contexts use
`hexe.family-identity-authorization.v1`, expire after at most 120 seconds, and
contain opaque identifiers and policy results rather than profiles, raw memory,
transcripts, or biometric material.
