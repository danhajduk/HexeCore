import asyncio
import json
import os
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.web_conversations import ConversationStore, build_conversation_router
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


class _Executor:
    async def execute(self, *, conversation_id, text, history):
        return f"reply:{text}"


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
