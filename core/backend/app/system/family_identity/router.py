from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.admin import admin_request_actor, require_admin_token
from app.system.audit import AuditLogStore
from app.system.auth.human import authenticate_human_token
from app.system.auth.tokens import ServiceTokenKeyStore
from app.system.users.store import UsersStore
from .store import FamilyIdentityError, FamilyIdentityStore


class StepUp(BaseModel):
    reauth_password: str | None = Field(default=None, max_length=256)
class HouseholdBody(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=120)
class PersonBody(StepUp):
    household_id: str = Field(..., min_length=8, max_length=160)
    display_name: str = Field(..., min_length=1, max_length=120)
    age_band: str | None = None
class PersonUpdate(StepUp):
    display_name: str = Field(..., min_length=1, max_length=120)
    age_band: str | None = None
    expected_version: int = Field(..., ge=1)
    archive: bool = False
class LinkBody(StepUp):
    person_id: str
    user_id: str
class GuardianBody(StepUp):
    guardian_person_id: str
    dependent_person_id: str
    purposes: list[str]
    operations: list[str]
    expires_at: str | None = None
class ConsentBody(StepUp):
    person_id: str
    purpose: str
    decision: str
    visibility: list[str]
    actor_person_id: str | None = None
    expires_at: str | None = None
class RoomBody(BaseModel):
    household_id: str
    display_name: str
    audience_mode: str = "household"
class AssignmentBody(BaseModel):
    endpoint_id: str
    room_id: str
class LifecycleBody(StepUp):
    person_id: str
    kind: str


def build_family_identity_router(store: FamilyIdentityStore, users: UsersStore, keys: ServiceTokenKeyStore, audit: AuditLogStore | None = None) -> APIRouter:
    router = APIRouter()

    async def actor(request: Request, admin_token: str | None, authorization: str | None):
        if authorization:
            principal = await authenticate_human_token(authorization, keys, users)
            principal.require("people.manage")
            return principal.user_id, principal.role, principal
        require_admin_token(admin_token, request)
        actor_id, role = admin_request_actor(request)
        return actor_id, role, None

    async def step_up(principal, password: str | None):
        if principal is None:
            return
        if not password:
            raise HTTPException(status_code=403, detail="reauthentication_required")
        verified = await users.verify_credentials(principal.username, password)
        if verified is None or str(verified["user_id"]) != principal.user_id:
            raise HTTPException(status_code=403, detail="reauthentication_failed")

    async def record(kind: str, actor_id: str, role: str, ids: dict):
        if audit:
            await audit.record(event_type=kind, actor_role=role, actor_id=actor_id, details=ids)

    async def invoke(fn, *args):
        try:
            return await fn(*args)
        except FamilyIdentityError as exc:
            code = str(exc)
            raise HTTPException(status_code=409 if code in {"version_conflict", "user_or_person_already_linked"} else 400, detail=code) from exc

    @router.get("/family/me")
    async def self_view(authorization: str | None = Header(default=None)):
        principal = await authenticate_human_token(authorization, keys, users)
        principal.require("people.self")
        return {"ok": True, **await store.self_view(principal.user_id)}

    @router.get("/family")
    async def snapshot(request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        await actor(request, x_admin_token, authorization)
        return {"ok": True, **await store.snapshot(), "users": await users.list_users()}

    @router.post("/family/households")
    async def household(body: HouseholdBody, request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_id, role, _ = await actor(request, x_admin_token, authorization)
        saved = await invoke(store.create_household, body.display_name)
        await record("family_household_created", actor_id, role, {"household_id": saved["household_id"]})
        return {"ok": True, "household": saved}

    @router.post("/family/people")
    async def person(body: PersonBody, request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_id, role, principal = await actor(request, x_admin_token, authorization)
        await step_up(principal, body.reauth_password)
        saved = await invoke(store.create_person, body.household_id, body.display_name, body.age_band)
        await record("family_person_created", actor_id, role, {"person_id": saved["person_id"], "household_id": saved["household_id"]})
        return {"ok": True, "person": saved}

    @router.put("/family/people/{person_id}")
    async def update_person(person_id: str, body: PersonUpdate, request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_id, role, principal = await actor(request, x_admin_token, authorization)
        await step_up(principal, body.reauth_password)
        saved = await invoke(store.update_person, person_id, body.display_name, body.age_band, body.expected_version, body.archive)
        await record("family_person_updated", actor_id, role, {"person_id": person_id, "version": saved["version"], "status": saved["status"]})
        return {"ok": True, "person": saved}

    @router.post("/family/user-links")
    async def link(body: LinkBody, request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_id, role, principal = await actor(request, x_admin_token, authorization); await step_up(principal, body.reauth_password)
        saved = await invoke(store.link_user, body.person_id, body.user_id, actor_id)
        await record("family_user_linked", actor_id, role, {"person_id": body.person_id, "user_id": body.user_id})
        return {"ok": True, "link": saved}

    @router.delete("/family/user-links/{person_id}")
    async def unlink(person_id: str, request: Request, body: StepUp | None = None, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_id, role, principal = await actor(request, x_admin_token, authorization); await step_up(principal, body.reauth_password if body else None)
        if not await store.unlink_user(person_id): raise HTTPException(status_code=404, detail="link_not_found")
        await record("family_user_unlinked", actor_id, role, {"person_id": person_id})
        return {"ok": True}

    @router.post("/family/guardians")
    async def guardian(body: GuardianBody, request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_id, role, principal = await actor(request, x_admin_token, authorization); await step_up(principal, body.reauth_password)
        saved = await invoke(store.create_guardian, body.guardian_person_id, body.dependent_person_id, body.purposes, body.operations, body.expires_at)
        await record("family_guardian_created", actor_id, role, {"relationship_id": saved["relationship_id"]})
        return {"ok": True, "guardian": saved}

    @router.post("/family/consents")
    async def consent(body: ConsentBody, request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_id, role, principal = await actor(request, x_admin_token, authorization); await step_up(principal, body.reauth_password)
        saved = await invoke(store.create_consent, body.person_id, body.purpose, body.decision, body.visibility, body.actor_person_id, body.expires_at)
        await record("family_consent_decided", actor_id, role, {"consent_id": saved["consent_id"], "person_id": body.person_id, "purpose": body.purpose, "decision": body.decision})
        return {"ok": True, "consent": saved}

    @router.post("/family/rooms")
    async def room(body: RoomBody, request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_id, role, _ = await actor(request, x_admin_token, authorization)
        saved = await invoke(store.create_room, body.household_id, body.display_name, body.audience_mode)
        await record("family_room_created", actor_id, role, {"room_id": saved["room_id"]})
        return {"ok": True, "room": saved}

    @router.post("/family/endpoint-assignments")
    async def assignment(body: AssignmentBody, request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_id, role, _ = await actor(request, x_admin_token, authorization)
        saved = await invoke(store.assign_endpoint, body.endpoint_id, body.room_id, actor_id)
        await record("family_endpoint_assigned", actor_id, role, {"endpoint_id": body.endpoint_id, "room_id": body.room_id})
        return {"ok": True, "assignment": saved}

    @router.post("/family/lifecycle")
    async def lifecycle(body: LifecycleBody, request: Request, x_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)):
        actor_id, role, principal = await actor(request, x_admin_token, authorization); await step_up(principal, body.reauth_password)
        saved = await invoke(store.request_lifecycle, body.person_id, body.kind, actor_id)
        await record("family_lifecycle_requested", actor_id, role, {"request_id": saved["request_id"], "person_id": body.person_id, "kind": body.kind})
        return {"ok": True, "request": saved}

    return router
