from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from app.system.audit import AuditLogStore
from app.system.auth import ServiceTokenKeyStore
from app.system.family_identity import FamilyIdentityStore, build_family_identity_router
from .identity_access import IdentityAccessEngine


@dataclass(frozen=True)
class PeopleHouseholdEngine:
    """Required Core owner for people, household, consent, and family policy state."""

    store: FamilyIdentityStore
    identity: IdentityAccessEngine
    keys: ServiceTokenKeyStore
    audit: AuditLogStore

    @classmethod
    def create(
        cls,
        *,
        database_path: str,
        core_id: str,
        identity: IdentityAccessEngine,
        keys: ServiceTokenKeyStore,
        audit: AuditLogStore,
    ) -> "PeopleHouseholdEngine":
        return cls(
            store=FamilyIdentityStore(database_path, core_id),
            identity=identity,
            keys=keys,
            audit=audit,
        )

    def mount_routes(self, app: FastAPI) -> None:
        for prefix, tag in (
            ("/api/admin", "admin-family-identity"),
            ("/api/web-app/admin", "web-app-admin-family-identity"),
        ):
            app.include_router(
                build_family_identity_router(self.store, self.identity.users, self.keys, self.audit),
                prefix=prefix,
                tags=[tag],
            )
