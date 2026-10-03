from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from app.core import (
    NotificationIntentStore,
    WebNotificationEventConsumer,
    WebNotificationPolicyService,
    WebPushGatewayBootstrapService,
    WebPushGatewayPublisher,
    WebPushRegistrationGrantIssuer,
    build_web_push_bootstrap_router,
    build_web_push_gateway_router,
    build_web_push_registration_router,
)
from app.system.audit import AuditLogStore
from app.system.settings.store import SettingsStore
from .identity_access import IdentityAccessEngine
from .people_household import PeopleHouseholdEngine


def _positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


@dataclass(frozen=True)
class WebPushTransport:
    """External transport adapter; it receives only policy-approved intents."""

    publisher: WebPushGatewayPublisher
    registration_issuer: WebPushRegistrationGrantIssuer
    bootstrap: WebPushGatewayBootstrapService

    @classmethod
    def from_environment(
        cls,
        *,
        intents: NotificationIntentStore,
        identity: IdentityAccessEngine,
        settings: SettingsStore,
        core_id: str,
    ) -> "WebPushTransport":
        credential_ref = str(os.getenv("HEXE_NOTIFICATION_GATEWAY_AUTH_REF", "notification_gateway_credential")).strip() or "notification_gateway_credential"
        audience = str(os.getenv("HEXE_NOTIFICATION_GATEWAY_AUDIENCE", "hexe-notification-gateway")).strip() or "hexe-notification-gateway"
        issuer = WebPushRegistrationGrantIssuer(
            settings,
            gateway_url=str(os.getenv("HEXE_NOTIFICATION_GATEWAY_REGISTRATION_URL", "")).strip(),
            gateway_audience=audience,
            vapid_public_key=str(os.getenv("HEXE_NOTIFICATION_GATEWAY_VAPID_PUBLIC_KEY", "")).strip(),
            credential_ref=credential_ref,
            ttl_seconds=_positive_int("HEXE_NOTIFICATION_GATEWAY_REGISTRATION_GRANT_TTL_SECONDS", 120),
        )
        return cls(
            publisher=WebPushGatewayPublisher(
                intents,
                identity.devices,
                settings,
                core_id=core_id,
                gateway_url=str(os.getenv("HEXE_NOTIFICATION_GATEWAY_URL", "")).strip(),
                credential_ref=credential_ref,
                audience=audience,
                max_attempts=_positive_int("HEXE_NOTIFICATION_GATEWAY_MAX_ATTEMPTS", 8),
            ),
            registration_issuer=issuer,
            bootstrap=WebPushGatewayBootstrapService(
                settings,
                issuer,
                bootstrap_url=str(os.getenv("HEXE_NOTIFICATION_GATEWAY_BOOTSTRAP_URL", "")).strip(),
                credential_ref=credential_ref,
            ),
        )


@dataclass(frozen=True)
class NotificationPolicyEngine:
    """Required Core owner for recipient policy, privacy, and delivery intents."""

    intents: NotificationIntentStore
    policy: WebNotificationPolicyService
    event_consumer: WebNotificationEventConsumer
    transport: WebPushTransport
    identity: IdentityAccessEngine
    people: PeopleHouseholdEngine

    @classmethod
    def create(
        cls,
        *,
        database_path: str,
        core_id: str,
        identity: IdentityAccessEngine,
        people: PeopleHouseholdEngine,
        settings: SettingsStore,
        audit: AuditLogStore,
        mqtt_manager: Any,
    ) -> "NotificationPolicyEngine":
        intents = NotificationIntentStore(database_path)
        policy = WebNotificationPolicyService(identity.devices, intents, core_id=core_id, audit=audit)
        transport = WebPushTransport.from_environment(intents=intents, identity=identity, settings=settings, core_id=core_id)
        return cls(
            intents=intents,
            policy=policy,
            event_consumer=WebNotificationEventConsumer(mqtt_manager, policy, core_id=core_id),
            transport=transport,
            identity=identity,
            people=people,
        )

    def mount_transport_routes(self, app: FastAPI, settings: SettingsStore, audit: AuditLogStore) -> None:
        app.include_router(
            build_web_push_gateway_router(self.transport.publisher, self.identity.keys, self.identity.users, audit),
            prefix="/api/web-app",
            tags=["web-push-gateway"],
        )
        app.include_router(
            build_web_push_registration_router(self.transport.registration_issuer, self.identity.keys, self.identity.users, self.identity.devices, settings),
            prefix="/api/web-app",
            tags=["web-push-registration"],
        )
        app.include_router(
            build_web_push_bootstrap_router(self.transport.bootstrap, self.identity.keys, self.identity.users, settings, audit),
            prefix="/api/web-app",
            tags=["web-push-bootstrap"],
        )
