from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from app.api.admin import configure_admin_users_store
from app.system.audit import AuditLogStore
from app.system.assistant_auth.service import AssistantAssertionService
from app.system.auth import (
    ServiceTokenKeyStore,
    WebAppEnrollmentStore,
    build_device_enrollment_router,
    build_human_auth_router,
)
from app.system.settings.store import SettingsStore
from app.system.users import UsersStore, build_users_router


@dataclass(frozen=True)
class IdentityAccessEngine:
    """Required Core owner for human principals, sessions, and enrolled devices."""

    users: UsersStore
    devices: WebAppEnrollmentStore
    keys: ServiceTokenKeyStore
    settings: SettingsStore
    audit: AuditLogStore
    assistant_assertions: AssistantAssertionService | None = None

    @classmethod
    def create(
        cls,
        *,
        database_path: str,
        keys: ServiceTokenKeyStore,
        settings: SettingsStore,
        audit: AuditLogStore,
        assistant_assertions: AssistantAssertionService | None = None,
    ) -> "IdentityAccessEngine":
        return cls(
            users=UsersStore(database_path),
            devices=WebAppEnrollmentStore(database_path),
            keys=keys,
            settings=settings,
            audit=audit,
            assistant_assertions=assistant_assertions,
        )

    def mount_admin_routes(self, app: FastAPI) -> None:
        configure_admin_users_store(self.users)
        app.include_router(
            build_users_router(self.users, self.audit, self.keys, self.devices, self.assistant_assertions),
            prefix="/api/admin",
            tags=["admin-users"],
        )
        app.include_router(
            build_users_router(self.users, self.audit, self.keys, self.devices, self.assistant_assertions),
            prefix="/api/web-app/admin",
            tags=["web-app-admin-users"],
        )

    def mount_authentication_routes(self, app: FastAPI) -> None:
        app.include_router(
            build_human_auth_router(self.keys, self.users, self.audit, self.assistant_assertions),
            prefix="/api/auth",
            tags=["human-auth"],
        )
        app.include_router(
            build_device_enrollment_router(self.devices, self.users, self.keys, self.audit, self.settings, self.assistant_assertions),
            prefix="/api/auth",
            tags=["web-app-enrollment"],
        )
