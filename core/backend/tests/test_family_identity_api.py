import asyncio
import os
import tempfile
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.system.auth import ServiceTokenKeyStore, build_human_auth_router
from app.system.family_identity import FamilyIdentityStore, build_family_identity_router
from app.system.settings.store import SettingsStore
from app.system.assistant_auth import AssistantAssertionService
from app.system.users import UsersStore


def test_people_are_distinct_from_users_and_sensitive_changes_require_step_up():
    with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"HEXE_CORE_ID": "core-family-test"}):
        db = os.path.join(temporary, "users.db")
        users = UsersStore(db)
        owner = asyncio.run(users.upsert_user(username="Owner", role="owner", enabled=True, password="owner-pass"))
        member = asyncio.run(users.upsert_user(username="Member", role="member", enabled=True, password="member-pass"))
        settings = SettingsStore(os.path.join(temporary, "settings.db"))
        keys = ServiceTokenKeyStore(settings)
        family = FamilyIdentityStore(db, "core-family-test")
        assistant_assertions = AssistantAssertionService(settings)
        app = FastAPI()
        app.include_router(build_human_auth_router(keys, users), prefix="/api/auth")
        app.include_router(
            build_family_identity_router(family, users, keys, assistant_assertions=assistant_assertions),
            prefix="/api/web-app/admin",
        )
        client = TestClient(app)
        login = client.post("/api/auth/user/login", json={"username": "Owner", "password": "owner-pass"}).json()
        auth = {"Authorization": f"Bearer {login['access_token']}"}

        household = client.post("/api/web-app/admin/family/households", headers=auth, json={"display_name": "Home"})
        assert household.status_code == 200
        household_id = household.json()["household"]["household_id"]
        denied = client.post("/api/web-app/admin/family/people", headers=auth, json={"household_id": household_id, "display_name": "Alex"})
        assert denied.status_code == 403
        person = client.post("/api/web-app/admin/family/people", headers=auth, json={"household_id": household_id, "display_name": "Alex", "age_band": "adult", "reauth_password": "owner-pass"})
        assert person.status_code == 200, person.text
        person_id = person.json()["person"]["person_id"]
        link = client.post("/api/web-app/admin/family/user-links", headers=auth, json={"person_id": person_id, "user_id": member["user_id"], "reauth_password": "owner-pass"})
        assert link.status_code == 200, link.text
        linked_epochs = asyncio.run(
            assistant_assertions.authorization_epochs(
                user_id=member["user_id"], device_id=None, node_id="core", household_id=household_id
            )
        )
        assert linked_epochs["user"] == 1
        assert linked_epochs["household"] == 1

        unlink = client.request(
            "DELETE",
            f"/api/web-app/admin/family/user-links/{person_id}",
            headers=auth,
            json={"reauth_password": "owner-pass"},
        )
        assert unlink.status_code == 200, unlink.text
        unlinked_epochs = asyncio.run(
            assistant_assertions.authorization_epochs(
                user_id=member["user_id"], device_id=None, node_id="core", household_id=household_id
            )
        )
        assert unlinked_epochs["user"] == 2
        assert unlinked_epochs["household"] == 2

        relink = client.post("/api/web-app/admin/family/user-links", headers=auth, json={"person_id": person_id, "user_id": member["user_id"], "reauth_password": "owner-pass"})
        assert relink.status_code == 200, relink.text

        snapshot = client.get("/api/web-app/admin/family", headers=auth).json()
        assert snapshot["people"][0]["person_id"] != owner["user_id"]
        assert snapshot["user_links"][0]["user_id"] == member["user_id"]
        assert snapshot["users"][0].get("password_hash") is None
        member_login = client.post("/api/auth/user/login", json={"username": "Member", "password": "member-pass"}).json()
        own = client.get("/api/web-app/admin/family/me", headers={"Authorization": f"Bearer {member_login['access_token']}"})
        assert own.status_code == 200
        assert own.json()["person"]["person_id"] == person_id


def test_cardinality_version_consent_guardian_and_lifecycle_boundaries():
    with tempfile.TemporaryDirectory() as temporary:
        db = os.path.join(temporary, "users.db")
        users = UsersStore(db)
        user = asyncio.run(users.upsert_user(username="User", role="member", enabled=True, password="pass"))
        family = FamilyIdentityStore(db, "core-one")
        household = asyncio.run(family.create_household("Home"))
        guardian = asyncio.run(family.create_person(household["household_id"], "Guardian", "adult"))
        dependent = asyncio.run(family.create_person(household["household_id"], "Dependent", "child"))
        asyncio.run(family.link_user(guardian["person_id"], user["user_id"], "actor"))

        try:
            asyncio.run(family.link_user(dependent["person_id"], user["user_id"], "actor"))
            assert False, "one user must not link to two people"
        except RuntimeError as exc:
            assert str(exc) == "user_or_person_already_linked"
        relation = asyncio.run(family.create_guardian(guardian["person_id"], dependent["person_id"], ["memory.read"], ["export"], None))
        consent = asyncio.run(family.create_consent(dependent["person_id"], "memory.read", "denied", ["private"], guardian["person_id"], None))
        lifecycle = asyncio.run(family.request_lifecycle(dependent["person_id"], "delete", "actor"))
        assert relation["guardian_person_id"] == guardian["person_id"]
        assert consent["decision"] == "denied"
        assert lifecycle["state"] == "incomplete"
        denied = asyncio.run(family.authorization_context(user_id=user["user_id"], session_id="session", device_id=None, household_id=household["household_id"], operation="memory.read", risk="personal_sensitive", visibility=["private"], identity_state="authenticated"))
        assert denied["decision"]["effect"] == "deny"
        assert denied["decision"]["reason"] == "consent_required"
        try:
            asyncio.run(family.update_person(dependent["person_id"], "Dependent", "child", 99, False))
            assert False, "stale version must fail"
        except RuntimeError as exc:
            assert str(exc) == "version_conflict"


def test_database_isolation_by_core_id():
    with tempfile.TemporaryDirectory() as temporary:
        db = os.path.join(temporary, "users.db")
        one = FamilyIdentityStore(db, "core-one")
        two = FamilyIdentityStore(db, "core-two")
        asyncio.run(one.create_household("One"))
        asyncio.run(two.create_household("Two"))
        assert [item["display_name"] for item in asyncio.run(one.snapshot())["households"]] == ["One"]
        assert [item["display_name"] for item in asyncio.run(two.snapshot())["households"]] == ["Two"]
