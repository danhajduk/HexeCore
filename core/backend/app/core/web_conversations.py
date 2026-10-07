from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.system.audit import AuditLogStore
from app.system.assistant_auth import AssistantAssertionService
from app.system.family_identity import FamilyIdentityStore
from app.system.auth.device_enrollment import WebAppEnrollmentStore
from app.system.auth.human import HumanPrincipal, authenticate_human_token
from app.system.auth.tokens import ServiceTokenKeyStore, sign_hs256
from app.system.platform_identity import load_platform_identity
from app.system.services.store import ServiceCatalogStore
from app.system.service_access import ServiceAccessGrantStore
from app.system.service_access.router import SERVICE_TOKEN_ISSUER
from app.system.settings.store import SettingsStore
from app.system.users.store import UsersStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationCreate(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=120)


class ConversationMessage(BaseModel):
    text: str = Field(..., min_length=1, max_length=16_000)
    mode: str = Field(default="text", pattern="^(text|voice)$")


class ConversationStore:
    def __init__(self, db_path: str, *, retention_days: int = 30, max_messages: int = 200) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()
        self._retention_days, self._max_messages = max(1, retention_days), max(20, max_messages)
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS web_app_conversations (
          conversation_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT);
        CREATE TABLE IF NOT EXISTS web_app_conversation_messages (
          message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, user_id TEXT NOT NULL,
          role TEXT NOT NULL, content TEXT NOT NULL, mode TEXT NOT NULL, created_at TEXT NOT NULL,
          FOREIGN KEY(conversation_id) REFERENCES web_app_conversations(conversation_id));
        CREATE INDEX IF NOT EXISTS web_app_conversation_owner_idx ON web_app_conversations(user_id, updated_at);
        CREATE TABLE IF NOT EXISTS web_app_conversation_assistant_events (
          event_id TEXT PRIMARY KEY, turn_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
          user_id TEXT NOT NULL, sequence INTEGER NOT NULL, event_type TEXT NOT NULL,
          payload_json TEXT NOT NULL, occurred_at TEXT NOT NULL,
          UNIQUE(turn_id, sequence),
          FOREIGN KEY(conversation_id) REFERENCES web_app_conversations(conversation_id));
        CREATE INDEX IF NOT EXISTS web_app_assistant_event_owner_idx
          ON web_app_conversation_assistant_events(user_id, conversation_id, turn_id, sequence);
        """)

    async def create(self, user_id: str, title: str) -> dict[str, Any]:
        async with self._lock: return await asyncio.to_thread(self._create, user_id, title)
    def _create(self, user_id: str, title: str) -> dict[str, Any]:
        now, cid = _now(), f"conv_{uuid.uuid4().hex}"
        self._conn.execute("INSERT INTO web_app_conversations VALUES (?, ?, ?, ?, ?, NULL)", (cid, user_id, title.strip(), now, now))
        return dict(self._conn.execute("SELECT * FROM web_app_conversations WHERE conversation_id=?", (cid,)).fetchone())

    async def list(self, user_id: str) -> list[dict[str, Any]]:
        async with self._lock: return await asyncio.to_thread(self._list, user_id)
    def _list(self, user_id: str) -> list[dict[str, Any]]:
        cutoff=(datetime.now(timezone.utc)-timedelta(days=self._retention_days)).isoformat()
        self._conn.execute("UPDATE web_app_conversations SET deleted_at=? WHERE user_id=? AND deleted_at IS NULL AND updated_at<?", (_now(),user_id,cutoff))
        return [dict(row) for row in self._conn.execute("SELECT conversation_id,title,created_at,updated_at FROM web_app_conversations WHERE user_id=? AND deleted_at IS NULL ORDER BY updated_at DESC",(user_id,)).fetchall()]

    async def get(self, user_id: str, conversation_id: str) -> dict[str, Any] | None:
        async with self._lock: return await asyncio.to_thread(self._get, user_id, conversation_id)
    def _get(self, user_id: str, conversation_id: str) -> dict[str, Any] | None:
        row=self._conn.execute("SELECT * FROM web_app_conversations WHERE conversation_id=? AND user_id=? AND deleted_at IS NULL",(conversation_id,user_id)).fetchone()
        if row is None: return None
        messages=[dict(item) for item in self._conn.execute("SELECT message_id,role,content,mode,created_at FROM web_app_conversation_messages WHERE conversation_id=? AND user_id=? ORDER BY created_at,message_id",(conversation_id,user_id)).fetchall()]
        return dict(row)|{"messages":messages}

    async def append(self, user_id: str, conversation_id: str, role: str, content: str, mode: str) -> dict[str, Any] | None:
        async with self._lock: return await asyncio.to_thread(self._append, user_id, conversation_id, role, content, mode)
    def _append(self, user_id: str, conversation_id: str, role: str, content: str, mode: str) -> dict[str, Any] | None:
        if self._conn.execute("SELECT 1 FROM web_app_conversations WHERE conversation_id=? AND user_id=? AND deleted_at IS NULL",(conversation_id,user_id)).fetchone() is None: return None
        now,mid=_now(),f"msg_{uuid.uuid4().hex}"
        self._conn.execute("INSERT INTO web_app_conversation_messages VALUES (?, ?, ?, ?, ?, ?, ?)",(mid,conversation_id,user_id,role,content,mode,now))
        self._conn.execute("UPDATE web_app_conversations SET updated_at=? WHERE conversation_id=?",(now,conversation_id))
        excess=int(self._conn.execute("SELECT COUNT(*) FROM web_app_conversation_messages WHERE conversation_id=?",(conversation_id,)).fetchone()[0])-self._max_messages
        if excess>0: self._conn.execute("DELETE FROM web_app_conversation_messages WHERE message_id IN (SELECT message_id FROM web_app_conversation_messages WHERE conversation_id=? ORDER BY created_at,message_id LIMIT ?)",(conversation_id,excess))
        return {"message_id":mid,"role":role,"content":content,"mode":mode,"created_at":now}

    async def delete(self, user_id: str, conversation_id: str) -> bool:
        async with self._lock: return await asyncio.to_thread(self._delete, user_id, conversation_id)
    def _delete(self, user_id: str, conversation_id: str) -> bool:
        return self._conn.execute("UPDATE web_app_conversations SET deleted_at=? WHERE conversation_id=? AND user_id=? AND deleted_at IS NULL",(_now(),conversation_id,user_id)).rowcount==1

    async def append_assistant_events(self, user_id: str, conversation_id: str, turn_id: str, events: list[dict[str, Any]]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._append_assistant_events, user_id, conversation_id, turn_id, events)

    def _append_assistant_events(self, user_id: str, conversation_id: str, turn_id: str, events: list[dict[str, Any]]) -> None:
        owner = self._conn.execute(
            "SELECT 1 FROM web_app_conversations WHERE conversation_id=? AND user_id=? AND deleted_at IS NULL",
            (conversation_id, user_id),
        ).fetchone()
        if owner is None:
            raise RuntimeError("conversation_not_found")
        with self._conn:
            for event in events:
                payload = json.dumps(event, sort_keys=True, separators=(",", ":"))
                try:
                    self._conn.execute(
                        "INSERT INTO web_app_conversation_assistant_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(event["event_id"]), turn_id, conversation_id, user_id,
                            int(event["sequence"]), str(event["type"]), payload,
                            str(event["occurred_at"]),
                        ),
                    )
                except sqlite3.IntegrityError:
                    existing = self._conn.execute(
                        "SELECT payload_json FROM web_app_conversation_assistant_events WHERE turn_id=? AND sequence=?",
                        (turn_id, int(event["sequence"])),
                    ).fetchone()
                    if existing is None or str(existing["payload_json"]) != payload:
                        raise RuntimeError("assistant_event_conflict")

    async def assistant_events(self, user_id: str, conversation_id: str, turn_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._assistant_events, user_id, conversation_id, turn_id)

    def _assistant_events(self, user_id: str, conversation_id: str, turn_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT payload_json FROM web_app_conversation_assistant_events WHERE user_id=? AND conversation_id=? AND turn_id=? ORDER BY sequence",
            (user_id, conversation_id, turn_id),
        ).fetchall()
        return [json.loads(str(row["payload_json"])) for row in rows]


class CoreChatExecutor:
    def __init__(self, catalog: ServiceCatalogStore, grants: ServiceAccessGrantStore, keys: ServiceTokenKeyStore, settings: SettingsStore, *, assistant_assertions: AssistantAssertionService | None = None, family: FamilyIdentityStore | None = None, conversations: ConversationStore | None = None, client: httpx.AsyncClient | None = None) -> None:
        self._catalog,self._grants,self._keys,self._settings,self._client=catalog,grants,keys,settings,client
        self._assistant_assertions,self._family,self._conversations=assistant_assertions,family,conversations
    async def execute(self, *, conversation_id: str, text: str, history: list[dict[str, Any]], user_id: str | None = None, device_id: str | None = None, mode: str = "text") -> str:
        assistant=await self._catalog.resolve("interaction.assistant.turn")
        if assistant is not None:
            if not user_id or self._assistant_assertions is None or self._family is None or self._conversations is None:
                raise RuntimeError("assistant_core_context_unavailable")
            return await self._execute_assistant(service=assistant,conversation_id=conversation_id,text=text,history=history,user_id=user_id,device_id=device_id,mode=mode)
        service=await self._catalog.resolve("task.chat")
        if service is None: raise RuntimeError("assistant_provider_unavailable")
        endpoint=str(service.get("execution_endpoint_url") or service.get("endpoint") or service.get("base_url") or "").strip()
        if not endpoint: raise RuntimeError("assistant_provider_endpoint_missing")
        if not endpoint.rstrip("/").endswith("/api/execution/direct"): endpoint=urljoin(endpoint.rstrip("/")+"/","api/execution/direct")
        identity=await load_platform_identity(self._settings); subject=identity.core_id
        audience=str(service.get("service_id") or "").strip()
        if not audience: raise RuntimeError("assistant_provider_identity_missing")
        grant=self._grants.find_authorizing(subject_node_id=subject,audience=audience,required_scopes=["service.execute:task.chat"])
        if grant is None: raise RuntimeError("assistant_provider_not_authorized")
        now=int(time.time()); key=await self._keys.active_key()
        provider_node_id=audience.split(":",3)[1] if audience.startswith("node-service:") else None
        claims={"iss":SERVICE_TOKEN_ISSUER,"sub":subject,"aud":audience,"scp":["service.execute:task.chat"],"iat":now,"exp":now+120,"jti":f"access-{uuid.uuid4().hex}","token_use":"node_service_access","authorization_id":grant.grant_id,"provider_node_id":provider_node_id}
        token=sign_hs256({"alg":"HS256","typ":"JWT","kid":str(key["kid"])},claims,str(key["secret"])); await self._keys.record_token_expiry(kid=str(key["kid"]),exp=now+120)
        payload={"task_id":f"web-{uuid.uuid4().hex}","task_family":"task.chat","requested_by":subject,"service_id":subject,"inputs":{"text":text,"user_text":text,"conversation_id":conversation_id,"context":history[-20:]},"constraints":{},"response_mode":"sync","timeout_s":60,"trace_id":f"web-{uuid.uuid4().hex[:12]}"}
        client=self._client or httpx.AsyncClient(timeout=65)
        try: response=await client.post(endpoint,headers={"Authorization":f"Bearer {token}","X-Hexe-Requester-Node-Id":subject},json=payload)
        finally:
            if self._client is None: await client.aclose()
        response.raise_for_status(); data=response.json(); output=data.get("output") if isinstance(data.get("output"),dict) else {}
        reply=str(output.get("reply_text") or output.get("text") or data.get("reply_text") or data.get("text") or "").strip()
        if not reply: raise RuntimeError("assistant_provider_empty_response")
        return reply

    async def _execute_assistant(self, *, service: dict[str, Any], conversation_id: str, text: str, history: list[dict[str, Any]], user_id: str, device_id: str | None, mode: str) -> str:
        endpoint=str(service.get("execution_endpoint_url") or service.get("endpoint") or service.get("base_url") or "").strip()
        if not endpoint: raise RuntimeError("assistant_provider_endpoint_missing")
        if not endpoint.rstrip("/").endswith("/api/interaction/assistant/v1/turns"):
            endpoint=urljoin(endpoint.rstrip("/")+"/","api/interaction/assistant/v1/turns")
        identity=await load_platform_identity(self._settings); subject=identity.core_id
        audience=str(service.get("service_id") or "").strip()
        if not audience: raise RuntimeError("assistant_provider_identity_missing")
        scopes=["assistant.turn.submit"]
        grant=self._grants.find_authorizing(subject_node_id=subject,audience=audience,required_scopes=scopes)
        if grant is None: raise RuntimeError("assistant_provider_not_authorized")
        now=int(time.time()); key=await self._keys.active_key(); turn_id=f"turn_{uuid.uuid4().hex}"
        provider_node_id=audience.split(":",3)[1] if audience.startswith("node-service:") else None
        claims={"iss":SERVICE_TOKEN_ISSUER,"sub":subject,"aud":audience,"scp":scopes,"iat":now,"exp":now+120,"jti":f"access-{uuid.uuid4().hex}","token_use":"node_service_access","authorization_id":grant.grant_id,"provider_node_id":provider_node_id}
        service_token=sign_hs256({"alg":"HS256","typ":"JWT","kid":str(key["kid"])},claims,str(key["secret"])); await self._keys.record_token_expiry(kid=str(key["kid"]),exp=now+120)
        self_view=await self._family.self_view(user_id); person=self_view.get("person") if isinstance(self_view,dict) else None
        person_id=str(person.get("person_id") or "") if isinstance(person,dict) else ""
        household_id=str(person.get("household_id") or "") if isinstance(person,dict) else ""
        actor_token,_=await self._assistant_assertions.issue_actor_assertion(core_id=identity.core_id,audience=audience,requester_node_id=identity.core_id,conversation_id=conversation_id,turn_id=turn_id,actor_kind="human_user",identity_state="verified",scopes=scopes,user_id=user_id,person_id=person_id or None,household_id=household_id or None,device_id=device_id)
        payload={
            "contract_version":"assistant.turn.v1","turn_id":turn_id,"conversation_id":conversation_id,
            "requester":{"node_id":identity.core_id,"core_id":identity.core_id},
            "actor":{"actor_id":user_id,"actor_kind":"human_user","identity_state":"verified","user_id":user_id,"person_id":person_id or None,"confidence":None,"evidence":[]},
            "input":{"mode":"voice_transcript" if mode=="voice" else "text","text":text,"language":"en-US","transcript_id":f"transcript_{uuid.uuid4().hex}" if mode=="voice" else None},
            "context":{"locale":"en-US","time_zone":"UTC","device_id":device_id,"room_id":None,"endpoint_id":None,"history":history[-20:],"summary":None},
            "authorization":{"actor_assertion":actor_token,"requested_scopes":scopes},
            "delivery":{"after_sequence":0},
        }
        client=self._client or httpx.AsyncClient(timeout=65)
        try: response=await client.post(endpoint,headers={"Authorization":f"Bearer {service_token}","X-Hexe-Requester-Node-Id":subject,"Accept":"application/x-ndjson"},json=payload)
        finally:
            if self._client is None: await client.aclose()
        response.raise_for_status()
        if "application/x-ndjson" not in str(response.headers.get("content-type") or "").lower():
            raise RuntimeError("assistant_event_media_type_invalid")
        events=[]; expected_sequence=1; terminal=None; final_text=""
        for line in response.text.splitlines():
            if not line.strip(): continue
            try: event=json.loads(line)
            except json.JSONDecodeError as exc: raise RuntimeError("assistant_event_invalid_json") from exc
            if terminal is not None:
                raise RuntimeError("assistant_event_after_terminal")
            if event.get("contract_version")!="assistant.event.v1" or event.get("turn_id")!=turn_id or event.get("conversation_id")!=conversation_id or int(event.get("sequence") or 0)!=expected_sequence or not str(event.get("event_id") or "") or not str(event.get("occurred_at") or "") or not isinstance(event.get("data"),dict):
                raise RuntimeError("assistant_event_contract_invalid")
            expected_sequence+=1; events.append(event); event_type=str(event.get("type") or "")
            if event_type=="assistant.content.final": final_text=str((event.get("data") or {}).get("text") or "").strip()
            if event_type in {"assistant.turn.completed","assistant.turn.failed","assistant.turn.cancelled"}:
                terminal=event_type
        if terminal!="assistant.turn.completed": raise RuntimeError("assistant_turn_not_completed")
        if not final_text: raise RuntimeError("assistant_provider_empty_response")
        await self._conversations.append_assistant_events(user_id,conversation_id,turn_id,events)
        return final_text


def build_conversation_router(store: ConversationStore, executor: CoreChatExecutor, keys: ServiceTokenKeyStore, users: UsersStore, devices: WebAppEnrollmentStore, settings: SettingsStore, audit: AuditLogStore | None=None) -> APIRouter:
    router=APIRouter()
    async def principal(authorization: str | None) -> HumanPrincipal:
        value=await authenticate_human_token(authorization,keys,users)
        if not value.device_id: raise HTTPException(403,"enrolled_device_required")
        device=await devices.get_device(value.device_id); identity=await load_platform_identity(settings)
        if device is None or device.get("revoked_at") or not bool(device.get("enabled",True)) or str(device.get("user_id"))!=value.user_id or str(device.get("core_id"))!=identity.core_id: raise HTTPException(403,"enrolled_device_invalid")
        return value
    @router.get("/conversations")
    async def list_conversations(authorization: str|None=Header(default=None)):
        p=await principal(authorization); return {"ok":True,"items":await store.list(p.user_id)}
    @router.post("/conversations")
    async def create_conversation(body: ConversationCreate,authorization: str|None=Header(default=None)):
        p=await principal(authorization); item=await store.create(p.user_id,body.title)
        if audit: await audit.record(event_type="web_conversation_created",actor_role=p.role,actor_id=p.user_id,details={"conversation_id":item["conversation_id"]})
        return {"ok":True,"conversation":item}
    @router.get("/conversations/{conversation_id}")
    async def get_conversation(conversation_id: str,authorization: str|None=Header(default=None)):
        p=await principal(authorization); item=await store.get(p.user_id,conversation_id)
        if item is None: raise HTTPException(404,"conversation_not_found")
        return {"ok":True,"conversation":item}
    @router.delete("/conversations/{conversation_id}")
    async def delete_conversation(conversation_id: str,authorization: str|None=Header(default=None)):
        p=await principal(authorization)
        if not await store.delete(p.user_id,conversation_id): raise HTTPException(404,"conversation_not_found")
        if audit: await audit.record(event_type="web_conversation_deleted",actor_role=p.role,actor_id=p.user_id,details={"conversation_id":conversation_id})
        return {"ok":True}
    @router.post("/conversations/{conversation_id}/messages")
    async def send_message(conversation_id: str,body: ConversationMessage,authorization: str|None=Header(default=None)):
        p=await principal(authorization); user_message=await store.append(p.user_id,conversation_id,"user",body.text.strip(),body.mode)
        if user_message is None: raise HTTPException(404,"conversation_not_found")
        current=await store.get(p.user_id,conversation_id) or {"messages":[]}
        try: reply=await executor.execute(conversation_id=conversation_id,text=body.text.strip(),history=current["messages"],user_id=p.user_id,device_id=p.device_id,mode=body.mode)
        except (RuntimeError,httpx.HTTPError) as exc: raise HTTPException(503,str(exc)[:120]) from exc
        assistant=await store.append(p.user_id,conversation_id,"assistant",reply,"text")
        if audit: await audit.record(event_type="web_conversation_turn",actor_role=p.role,actor_id=p.user_id,details={"conversation_id":conversation_id,"mode":body.mode})
        return {"ok":True,"user_message":user_message,"assistant_message":assistant}
    @router.post("/conversations/{conversation_id}/messages/stream")
    async def stream_message(conversation_id: str,body: ConversationMessage,authorization: str|None=Header(default=None)):
        p=await principal(authorization)
        if await store.get(p.user_id,conversation_id) is None: raise HTTPException(404,"conversation_not_found")
        async def events():
            user_message=await store.append(p.user_id,conversation_id,"user",body.text.strip(),body.mode)
            yield json.dumps({"type":"conversation.message.accepted","message":user_message},separators=(",",":"))+"\n"
            current=await store.get(p.user_id,conversation_id) or {"messages":[]}
            try:
                reply=await executor.execute(conversation_id=conversation_id,text=body.text.strip(),history=current["messages"],user_id=p.user_id,device_id=p.device_id,mode=body.mode)
                assistant=await store.append(p.user_id,conversation_id,"assistant",reply,"text")
                if audit: await audit.record(event_type="web_conversation_turn",actor_role=p.role,actor_id=p.user_id,details={"conversation_id":conversation_id,"mode":body.mode})
                yield json.dumps({"type":"conversation.message.completed","message":assistant},separators=(",",":"))+"\n"
            except (RuntimeError,httpx.HTTPError):
                yield json.dumps({"type":"conversation.message.failed","error":"assistant_temporarily_unavailable"},separators=(",",":"))+"\n"
        return StreamingResponse(events(),media_type="application/x-ndjson",headers={"Cache-Control":"no-store","X-Accel-Buffering":"no"})
    return router
