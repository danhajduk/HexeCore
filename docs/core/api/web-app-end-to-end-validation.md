# Core Web App End-to-End Validation

Status: Implemented for the user-approved one-user validation scope; two-user
physical-device isolation is deferred to Task 1028

This record covers Core Task 1014 and the live validation performed on
2026-10-06. It complements the normative
[multi-user security contract](./multi-user-remote-web-app-security-contract.md);
it does not replace that contract.

## Ownership and Data Flow

1. The installed PWA is served by Core from
   `https://<core-id>.hexe-ai.com/app` and calls the same origin.
2. Cloudflare Tunnel supplies ingress and addressability only. It does not
   authenticate users or authorize APIs.
3. Supervisor owns the host-local `hexe-cloudflared.service` process and the
   redacted runtime configuration. Core owns tunnel publication policy.
4. Core authenticates the user, session, and enrolled device; owns
   conversations, preferences, recipient selection, quiet hours, privacy
   filtering, revocation, audit, and retry state.
5. The PWA sends Push API provider material directly to the Web Push gateway
   under a short-lived, single-use, device-bound Core grant. Core retains only
   the opaque subscription reference.
6. The Web Push gateway validates Core-bound grants and delivery assertions,
   stores provider subscription material, and performs transport delivery. It
   receives no Core human token, refresh token, administrator credential,
   family record, conversation, or unrestricted event payload.
7. A notification deep link returns to a Core-relative path. Protected detail
   is loaded only after Core authentication.

## Live Evidence

The live Core, Supervisor, tunnel, and gateway were running during this check.
The canonical Core hostname returned `307` from `/` to `/app`; `/app`, the web
manifest, and service worker returned `200`. The manifest uses `/app` as its
standalone start URL. Anonymous conversation, subscription-configuration, and
gateway-status requests returned `401`; the local-only administration API
returned `404`; and a disallowed browser origin returned `403`.

The production gateway returned `200` from both `/v1/health` and `/v1/ready`.
Core's sensitive settings contained an active Core-bound credential plus
registration, delivery, rotation, and revocation endpoints. The live durable
store contained four delivered notification intents. Credential values,
provider endpoints, raw subscriptions, and private keys were not inspected or
copied into this record.

The approved one-user live topology contained three active installed-device
records belonging to one user, one active push subscription, and two active
preference records belonging to that user's devices. Two conversations existed
for one user. Four historical notification intents for the active iPhone
subscription were accepted and recorded as delivered on their first gateway
attempt. A fresh acceptance event on 2026-10-06 was also created and accepted
by the gateway on its first attempt. The user then confirmed that iOS displayed
the fresh **Task update** notification, verifying the one-user Core-to-gateway-
to-iOS path. Gateway acceptance alone remains insufficient proof; this result
includes direct physical confirmation. This run does not claim cross-user
isolation or two-user delivery.

The acceptance check also exposed a separate app defect: Core persisted the
notification, but the PWA had no in-app notification surface and its deep link
targeted a route that did not exist. The PWA now reads the enrolled-device-
scoped `GET /api/web-app/notifications` feed, displays a notification panel,
refreshes it immediately on resume and every five seconds while visible, and uses
`/app/notifications` as the valid notification-click target. The feed omits
subscription references and user/device identifiers and is constrained by the
authenticated token's enrolled user and device.

On the tested iPhone, tapping a Web Push notification consistently launched
the installed app at its fixed `/app` start URL without dispatching a usable
`notificationclick` navigation or message handoff. The app therefore also
opens the panel once for each newly observed notification less than 24 hours
old, keyed by `event_id` in local browser storage. This provides deterministic
in-app presentation from the authenticated feed without weakening server-side
ownership checks or repeatedly reopening an already-seen event.

Physical acceptance completed on 2026-10-06. The user confirmed prompt iOS
delivery of the final test and confirmed that, after authentication refresh,
the app loaded 12 device-scoped notifications and automatically opened the
notification panel using the unseen-event feed fallback. Direct URL navigation,
transient worker messaging, and a one-time click marker were insufficient on
this iOS installation; the feed-driven fallback is the verified behavior.

Production push latency includes a gateway queue boundary. Core submits the
intent immediately, but the Website gateway currently drains its durable queue
on a once-per-minute cron. Normal latency is therefore approximately 0-60
seconds before provider delivery, plus APNs/iOS scheduling time. Immediate
post-enqueue delivery is Website-owned follow-up work; the minute cron remains
necessary for retries.

## Automated Verification

- Core frontend: 21 files and 100 tests passed; TypeScript and the production
  Vite build passed.
- Website gateway under its required Node 22 runtime: 15 gateway tests and 6
  edge-fallback tests passed, including bootstrap replay denial, atomic
  rotation/revocation, opaque subscription ownership, Safari subscription
  compatibility, safe outage fallback, and API failure redaction.
- Core backend security matrix: 107 focused tests passed after aligning the
  bootstrap expectation with the implemented `people.self` permission.
- OpenAPI snapshot and generated route appendix checks passed.
- The environment and mirror checks remain blocked by pre-existing
  Core/Supervisor source-mirror drift. In particular, the Supervisor mirror
  does not yet contain the Core web-app, identity-engine, conversation, and Web
  Push implementation files. Two unrelated Supervisor Bluetooth files also
  contain uncommitted user work and must not be overwritten by a bulk mirror
  repair.

## Physical Device Matrix

The following cases require real enrolled installations and are not verifiable
from repository tests or database state alone:

| Case | Android/Chromium | iOS Home Screen | 2026-10-06 result |
| --- | --- | --- | --- |
| Install and standalone launch | Browser install prompt or menu; HTTPS required | Safari **Add to Home Screen**; HTTPS required | Not verifiable from current repository state |
| Notification permission | Request only from the in-app user action | Request only from the installed Home Screen app | Not verifiable from current repository state |
| Closed-app notification | Service worker receives provider push | Home Screen web app receives APNs-backed web push | Not verifiable from current repository state |
| Notification click/deep link | Opens the same Core origin and reauthenticates as needed | Opens the same Core origin and reauthenticates as needed | Not verifiable from current repository state |
| Badge behavior | Browser/OS dependent | iOS version and permission dependent | Not verifiable from current repository state |

## Deferred Two-User Checklist

Task 1028 preserves the postponed original acceptance work:

1. Enroll two distinct users on separate physical installed apps, retain one
   active subscription per user, and record only opaque IDs and timestamps.
2. Verify conversation, session, device, preference, subscription, delivery,
   audit, and deep-link isolation for both users.
3. Exercise quiet hours, redaction, click routing, and supported badge behavior
   on Android/Chromium and iOS Home Screen.
4. Revoke one session, one device, and one user independently, then perform the
   explicit all-mobile-access revocation and confirm the documented blast
   radius each time.
5. Exercise expired/replayed enrollment, wrong-Core credentials, invalid
   origin, replayed gateway assertions, invalid subscriptions, Core outage,
   gateway outage, and retry after restart.
6. Repair Core/Supervisor source mirrors without discarding the unrelated
   Bluetooth work, then pass `python tools/check_repo_health.py`.
7. Add the resulting evidence and implementation commit to the shared request
   before completing or archiving it.

## Troubleshooting

- Public `/api/health` returning `404` is expected: the public route allow-list
  intentionally hides unrelated local APIs. Use the documented public PWA
  probes and authenticated role-specific routes instead.
- `401` means application authentication is absent or invalid; Tunnel reachability
  does not change it. `403` for a foreign `Origin` is an exact-origin defense.
- If browser push configuration is unavailable, check the safe authenticated
  bootstrap/gateway status first, then gateway `/v1/ready`; never print the
  sensitive settings record.
- If delivery is accepted but not observed, correlate the opaque intent and
  device identifiers across Core audit/outbox state and gateway redacted
  telemetry. Do not log the raw subscription endpoint.
- If the OS notification arrives but the in-app list is stale, reopen the
  notification panel or use **Refresh**. A visible app polls at five-second
  intervals; an expired or revoked enrolled session must reauthenticate.
- If a revoked device still appears in browser storage, server-side revocation
  remains authoritative. Clear the local installation only after preserving
  the server-side audit evidence.
