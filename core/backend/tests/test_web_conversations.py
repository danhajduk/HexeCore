import asyncio
import json
import os
import tempfile
from types import SimpleNamespace

import httpx

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.web_conversations import ConversationStore, CoreChatExecutor, build_conversation_router
from app.system.assistant_auth import AssistantAssertionService
from app.system.auth import ServiceTokenKeyStore, WebAppEnrollmentStore, build_human_auth_router
from app.system.settings.store import SettingsStore
from app.system.platform_identity import load_platform_identity
from app.system.users import UsersStore


class TestConversationStore:
    def setup_method(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ConversationStore(os.path.join(self.tmp.name, "users.db"), max_messages=20)

    def teardown_method(self):
        self.tmp.cleanup()

    def test_two_users_are_isolated_and_deletion_is_owner_scoped(self):
        alice = asyncio.run(self.store.create("alice", "Alice chat"))
        bob = asyncio.run(self.store.create("bob", "Bob chat"))
        asyncio.run(self.store.append("alice", alice["conversation_id"], "user", "private alice", "text"))
        assert asyncio.run(self.store.get("bob", alice["conversation_id"])) is None
        assert asyncio.run(self.store.append("bob", alice["conversation_id"], "user", "intrude", "text")) is None
        assert asyncio.run(self.store.delete("bob", alice["conversation_id"])) is False
        assert [item["conversation_id"] for item in asyncio.run(self.store.list("alice"))] == [alice["conversation_id"]]
        assert [item["conversation_id"] for item in asyncio.run(self.store.list("bob"))] == [bob["conversation_id"]]

    def test_history_is_bounded(self):
        conversation = asyncio.run(self.store.create("alice", "Bounded"))
        for index in range(25):
            asyncio.run(self.store.append("alice", conversation["conversation_id"], "user", f"message {index}", "text"))
        loaded = asyncio.run(self.store.get("alice", conversation["conversation_id"]))
        assert loaded is not None
        assert len(loaded["messages"]) == 20
        assert loaded["messages"][0]["content"] == "message 5"

    def test_assistant_events_are_idempotent_and_owner_scoped(self):
        conversation = asyncio.run(self.store.create("alice", "Events"))
        event = {"contract_version":"assistant.event.v1","event_id":"evt-1","turn_id":"turn-1","conversation_id":conversation["conversation_id"],"sequence":1,"type":"assistant.turn.accepted","occurred_at":"2026-10-07T04:00:00Z","data":{}}
        asyncio.run(self.store.append_assistant_events("alice", conversation["conversation_id"], "turn-1", [event]))
        asyncio.run(self.store.append_assistant_events("alice", conversation["conversation_id"], "turn-1", [event]))
        assert asyncio.run(self.store.assistant_events("alice", conversation["conversation_id"], "turn-1")) == [event]
        assert asyncio.run(self.store.assistant_events("bob", conversation["conversation_id"], "turn-1")) == []


class _Executor:
    async def execute(self, *, conversation_id, text, history, **_context):
        return f"reply:{text}"


def test_core_executor_prefers_assistant_contract_and_persists_ordered_events(tmp_path):
    settings = SettingsStore(str(tmp_path / "settings.db"))
    keys = ServiceTokenKeyStore(settings)
    assertions = AssistantAssertionService(settings)
    store = ConversationStore(str(tmp_path / "conversations.db"))
    conversation = asyncio.run(store.create("user-1", "Assistant"))
    core_id = asyncio.run(load_platform_identity(settings)).core_id
    audience = "node-service:node-interaction-1:interaction.assistant.turn"

    class Catalog:
        async def resolve(self, capability):
            assert capability == "interaction.assistant.turn"
            return {"service_id": audience, "base_url": "http://interaction.local:9005"}

    class Grants:
        def find_authorizing(self, **kwargs):
            assert kwargs == {"subject_node_id": core_id, "audience": audience, "required_scopes": ["assistant.turn.submit"]}
            return SimpleNamespace(grant_id="grant-1")

    class Family:
        async def self_view(self, user_id):
            assert user_id == "user-1"
            return {"linked": True, "person": {"person_id": "person-1", "household_id": "household-1"}}

    async def handler(request):
        payload = json.loads(request.content)
        assert request.url.path == "/api/interaction/assistant/v1/turns"
        assert payload["actor"]["user_id"] == "user-1"
        assert payload["actor"]["person_id"] == "person-1"
        assert payload["authorization"]["actor_assertion"].count(".") == 2
        events = [
            {"contract_version":"assistant.event.v1","event_id":"evt-1","turn_id":payload["turn_id"],"conversation_id":payload["conversation_id"],"sequence":1,"type":"assistant.turn.accepted","occurred_at":"2026-10-07T04:00:00Z","data":{}},
            {"contract_version":"assistant.event.v1","event_id":"evt-2","turn_id":payload["turn_id"],"conversation_id":payload["conversation_id"],"sequence":2,"type":"assistant.content.final","occurred_at":"2026-10-07T04:00:01Z","data":{"text":"Assistant reply"}},
            {"contract_version":"assistant.event.v1","event_id":"evt-3","turn_id":payload["turn_id"],"conversation_id":payload["conversation_id"],"sequence":3,"type":"assistant.turn.completed","occurred_at":"2026-10-07T04:00:02Z","data":{}},
        ]
        return httpx.Response(200, headers={"content-type":"application/x-ndjson"}, text="\n".join(json.dumps(event) for event in events))

    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            executor = CoreChatExecutor(Catalog(), Grants(), keys, settings, assistant_assertions=assertions, family=Family(), conversations=store, client=client)
            return await executor.execute(conversation_id=conversation["conversation_id"], text="hello", history=[], user_id="user-1", device_id="device-1")

    assert asyncio.run(execute()) == "Assistant reply"
    rows = store._conn.execute("SELECT turn_id FROM web_app_conversation_assistant_events LIMIT 1").fetchall()
    assert len(rows) == 1
    events = asyncio.run(store.assistant_events("user-1", conversation["conversation_id"], str(rows[0]["turn_id"])))
    assert [event["type"] for event in events] == ["assistant.turn.accepted", "assistant.content.final", "assistant.turn.completed"]


class TestConversationApi:
    def setup_method(self):
        self.tmp=tempfile.TemporaryDirectory(); path=os.path.join(self.tmp.name,"users.db")
        self.settings=SettingsStore(os.path.join(self.tmp.name,"settings.db")); self.keys=ServiceTokenKeyStore(self.settings); self.users=UsersStore(path); self.devices=WebAppEnrollmentStore(path); self.store=ConversationStore(path); core_id=asyncio.run(load_platform_identity(self.settings)).core_id
        for name in ("alice","bob"): asyncio.run(self.users.upsert_user(username=name,role="member",enabled=True,password=f"{name}-pass"))
        now="2026-09-30T00:00:00+00:00"
        for name in ("alice","bob"):
            user=asyncio.run(self.users.get_user(name)); self.devices._conn.execute("INSERT INTO web_app_devices VALUES (?, ?, ?, ?, 'public-key', 'test', ?, ?, NULL)",(f"{name}-phone",core_id,user["user_id"],f"{name} phone",now,now))
        app=FastAPI(); app.include_router(build_human_auth_router(self.keys,self.users),prefix="/api/auth"); app.include_router(build_conversation_router(self.store,_Executor(),self.keys,self.users,self.devices,self.settings),prefix="/api/web-app"); self.client=TestClient(app)
    def teardown_method(self): self.tmp.cleanup()
    def token(self,name):
        response=self.client.post("/api/auth/user/login",json={"username":name,"password":f"{name}-pass","device_id":f"{name}-phone"}); assert response.status_code==200; return response.json()["access_token"]
    def test_authenticated_turn_and_cross_user_denial(self):
        alice={"Authorization":f"Bearer {self.token('alice')}"}; bob={"Authorization":f"Bearer {self.token('bob')}"}
        created=self.client.post("/api/web-app/conversations",headers=alice,json={"title":"Private"}); assert created.status_code==200
        cid=created.json()["conversation"]["conversation_id"]
        turn=self.client.post(f"/api/web-app/conversations/{cid}/messages",headers=alice,json={"text":"hello","mode":"voice"}); assert turn.status_code==200; assert turn.json()["assistant_message"]["content"]=="reply:hello"
        assert self.client.get(f"/api/web-app/conversations/{cid}",headers=bob).status_code==404
        assert self.client.delete(f"/api/web-app/conversations/{cid}",headers=bob).status_code==404
        assert self.client.get("/api/web-app/conversations").status_code==401
        streamed=self.client.post(f"/api/web-app/conversations/{cid}/messages/stream",headers=alice,json={"text":"stream me","mode":"text"})
        assert streamed.status_code==200
        assert [json.loads(line)["type"] for line in streamed.text.splitlines()] == ["conversation.message.accepted","conversation.message.completed"]
