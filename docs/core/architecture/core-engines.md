# Required Core Engines

Core organizes identity, people, and notification behavior as required internal
engines. They are not installable add-ons: Core cannot safely authenticate a
user, authorize access, or select notification recipients if one is absent.

| Engine | Owns | Depends on |
|---|---|---|
| Identity and Access | users, roles, sessions, passkeys, enrolled devices, revocation, step-up authentication | none |
| People and Household | people, households, links, relationships, consent, rooms, family authorization | Identity and Access |
| Notification Policy | preferences, recipients, privacy filtering, deduplication, quiet hours, delivery intents | Identity and Access; People and Household |
| Web Push Transport | gateway credentials, VAPID provisioning, browser subscription transport, delivery retries | Notification Policy |

The in-process engine registry validates ownership and dependencies during Core
composition. Its diagnostic snapshot contains only engine identifiers,
capability ownership, dependencies, and required/optional state.

`IdentityAccessEngine` is the composition owner for the human-user and
enrolled-device stores and mounts their existing administration,
authentication, session, and device-enrollment routes. Compatibility aliases
remain in application state while dependent subsystems migrate to narrower
engine service interfaces.

Add-ons and trusted nodes may produce validated events. They do not select
recipients or bypass consent and notification policy. The external Web Push
gateway transports already-authorized, privacy-filtered intents and receives no
Core human/admin credentials or family records.
