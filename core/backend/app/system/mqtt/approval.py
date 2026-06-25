from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .authority_policy import validate_authority_topic_access
from .integration_models import (
    MqttAddonGrant,
    MqttBrokerModeSummary,
    MqttNodeBridgeGrant,
    MqttPrincipal,
    MqttRegistrationApprovalResult,
    MqttRegistrationRequest,
    MqttSetupCapabilitySummary,
    MqttSetupStateUpdate,
)
from .integration_state import MqttIntegrationStateStore
from .topic_families import is_hexe_topic, is_node_scoped_topic, is_platform_reserved_topic
from .topic_policy import validate_topic_scopes


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_valid_topic_filter(topic: str) -> bool:
    value = str(topic or "").strip()
    if not value or "//" in value:
        return False
    levels = value.split("/")
    for idx, level in enumerate(levels):
        if "#" in level and (level != "#" or idx != len(levels) - 1):
            return False
        if "+" in level and level != "+":
            return False
    return True


def _first_invalid_topic(topics: list[str] | None) -> str | None:
    for topic in topics or []:
        normalized = str(topic or "").strip()
        if not _is_valid_topic_filter(normalized):
            return normalized
    return None


def _clean_topic_list(topics: list[str] | None) -> list[str]:
    return sorted({str(topic or "").strip() for topic in (topics or []) if str(topic or "").strip()})


def _bridge_grant_id(node_id: str, bridge_id: str) -> str:
    return f"{node_id}:{bridge_id}"


def _bridge_principal_id(grant_id: str) -> str:
    return f"bridge:{grant_id}"


def _bridge_username(node_id: str, bridge_id: str) -> str:
    node_part = str(node_id or "").strip().replace("node-", "")
    return f"hb_{node_part[:16]}_{bridge_id}"


def _bridge_topic_errors(*, node_id: str, publish_topics: list[str], subscribe_topics: list[str]) -> list[str]:
    errors: list[str] = []
    for topic in publish_topics:
        if is_hexe_topic(topic):
            if is_platform_reserved_topic(topic):
                errors.append(f"publish topic '{topic}' is reserved")
            elif not is_node_scoped_topic(topic, node_id=node_id):
                errors.append(f"publish topic '{topic}' must be external or under hexe/nodes/{node_id}/...")
    for topic in subscribe_topics:
        if is_hexe_topic(topic):
            if is_platform_reserved_topic(topic):
                errors.append(f"subscribe topic '{topic}' is reserved")
            elif not is_node_scoped_topic(topic, node_id=node_id):
                errors.append(f"subscribe topic '{topic}' must be external or under hexe/nodes/{node_id}/...")
    return sorted(set(errors))


class MqttRegistrationApprovalService:
    def __init__(
        self,
        *,
        registry,
        state_store: MqttIntegrationStateStore,
        observability_store=None,
        runtime_reconcile_hook=None,
        audit_store=None,
        credential_rotate_hook=None,
    ) -> None:
        self._registry = registry
        self._state_store = state_store
        self._observability = observability_store
        self._runtime_reconcile_hook = runtime_reconcile_hook
        self._audit = audit_store
        self._credential_rotate_hook = credential_rotate_hook

    async def approve(self, request: MqttRegistrationRequest, *, requested_by_subject: str | None = None) -> MqttRegistrationApprovalResult:
        addon_id = request.addon_id.strip()
        if requested_by_subject and requested_by_subject != addon_id:
            return MqttRegistrationApprovalResult(
                addon_id=addon_id or request.addon_id,
                status="rejected",
                access_mode=request.access_mode,
                reason="request_subject_mismatch: service token subject must match addon_id",
            )
        if not addon_id:
            return MqttRegistrationApprovalResult(
                addon_id=request.addon_id,
                status="rejected",
                access_mode=request.access_mode,
                reason="addon_id_required",
            )
        if not self._registry.has_addon(addon_id):
            return MqttRegistrationApprovalResult(
                addon_id=addon_id,
                status="rejected",
                access_mode=request.access_mode,
                reason=f"addon_not_found: '{addon_id}' is not registered in Core",
            )
        if not self._registry.is_enabled(addon_id):
            return MqttRegistrationApprovalResult(
                addon_id=addon_id,
                status="rejected",
                access_mode=request.access_mode,
                reason=f"addon_disabled: '{addon_id}' must be enabled before requesting MQTT access",
            )
        topic_errors = validate_topic_scopes(addon_id, request.publish_topics, request.subscribe_topics)
        if topic_errors:
            await self._record_observability(
                event_type="denied_topic_attempt",
                severity="warn",
                metadata={"addon_id": addon_id, "errors": topic_errors},
            )
            await self._append_audit(
                event_type="mqtt_topic_violation",
                status="warn",
                message="addon_scope_rejected",
                payload={"addon_id": addon_id, "errors": topic_errors},
            )
            return MqttRegistrationApprovalResult(
                addon_id=addon_id,
                status="rejected",
                access_mode=request.access_mode,
                reason="topic_scope_invalid: " + "; ".join(topic_errors),
            )

        approved = MqttRegistrationApprovalResult(
            addon_id=addon_id,
            status="approved",
            access_mode=request.access_mode,
            approved_publish_topics=sorted({str(x).strip() for x in request.publish_topics if str(x).strip()}),
            approved_subscribe_topics=sorted({str(x).strip() for x in request.subscribe_topics if str(x).strip()}),
        )
        state_before = await self._state_store.get_state()
        existing = state_before.active_grants.get(addon_id)
        grant = MqttAddonGrant(
            addon_id=addon_id,
            access_mode=approved.access_mode,
            status="approved",
            publish_topics=approved.approved_publish_topics,
            subscribe_topics=approved.approved_subscribe_topics,
            granted_ha_mode=request.capabilities.ha_discovery,
            access_profile=approved.access_mode,
            provision_contract=(existing.provision_contract if existing else {}),
            last_error=None,
            revocation_pending=False,
            last_provisioned_at=(existing.last_provisioned_at if existing else None),
            last_revoked_at=(existing.last_revoked_at if existing else None),
        )
        await self._state_store.upsert_grant(grant)
        prior_principal = state_before.principals.get(f"addon:{addon_id}")
        await self._state_store.upsert_principal(self._principal_from_grant(grant))
        await self._reconcile_runtime_if_needed(reason=f"approve:{addon_id}")
        await self._append_audit(
            event_type="mqtt_principal_action",
            status="ok",
            message="approve_grant",
            payload={"addon_id": addon_id},
        )
        if prior_principal is None:
            await self._append_lifecycle_audit("principal_created", principal_id=f"addon:{addon_id}", actor="authority")
        if existing is not None and self._grant_materially_changed(existing, grant) and existing.status in {"approved", "provisioned", "error"}:
            await self.provision_grant(addon_id, reason="grant_scope_changed")
        return approved

    async def provision_grant(self, addon_id: str, reason: str = "api_request") -> dict[str, Any]:
        state = await self._state_store.get_state()
        current = state.active_grants.get(addon_id)
        if current is None:
            return {"ok": False, "addon_id": addon_id, "status": "error", "error": "grant_not_found"}
        if not self._setup_ready(state):
            next_grant = current.model_copy(deep=True)
            next_grant.updated_at = _utcnow_iso()
            next_grant.status = "error"
            next_grant.last_error = f"mqtt_setup_not_ready:{state.setup_status}"
            await self._state_store.upsert_grant(next_grant)
            await self._record_observability(
                event_type="broker_readiness_issue",
                severity="warn",
                metadata={"addon_id": addon_id, "setup_status": state.setup_status},
            )
            return {
                "ok": False,
                "addon_id": addon_id,
                "status": "error",
                "error": "mqtt_setup_not_ready",
                "setup_status": state.setup_status,
            }
        next_grant = current.model_copy(deep=True)
        next_grant.updated_at = _utcnow_iso()
        next_grant.status = "active"
        next_grant.provision_contract = {
            "mode": "embedded_core_authority",
            "reason": reason,
            "applied_at": _utcnow_iso(),
        }
        next_grant.last_error = None
        next_grant.revocation_pending = False
        next_grant.last_provisioned_at = _utcnow_iso()
        await self._state_store.upsert_grant(next_grant)
        principal = self._principal_from_grant(next_grant)
        principal.status = "active"
        principal.last_activated_at = _utcnow_iso()
        await self._state_store.upsert_principal(principal)
        await self._reconcile_runtime_if_needed(reason=f"provision:{addon_id}")
        await self._append_audit(
            event_type="mqtt_principal_action",
            status="ok",
            message="provision_grant",
            payload={"addon_id": addon_id},
        )
        await self._append_lifecycle_audit("principal_activated", principal_id=principal.principal_id, actor="authority")
        details = {
            "mode": "embedded_core_authority",
            "reason": reason,
            "status": "applied",
        }
        return {"ok": True, "addon_id": addon_id, "status": next_grant.status, "details": details}

    async def revoke_or_mark(self, addon_id: str, reason: str) -> dict[str, Any]:
        state = await self._state_store.get_state()
        current = state.active_grants.get(addon_id)
        if current is None:
            return {"ok": True, "addon_id": addon_id, "status": "not_found"}
        next_grant = current.model_copy(deep=True)
        next_grant.updated_at = _utcnow_iso()
        next_grant.last_revoked_at = _utcnow_iso()
        next_grant.status = "revoked"
        next_grant.last_error = None
        next_grant.revocation_pending = False
        await self._state_store.upsert_grant(next_grant)
        principal = self._principal_from_grant(next_grant)
        principal.status = "revoked"
        principal.last_revoked_at = _utcnow_iso()
        await self._state_store.upsert_principal(principal)
        await self._reconcile_runtime_if_needed(reason=f"revoke:{addon_id}")
        await self._append_audit(
            event_type="mqtt_principal_action",
            status="ok",
            message="revoke_grant",
            payload={"addon_id": addon_id, "reason": reason},
        )
        await self._append_lifecycle_audit("principal_revoked", principal_id=principal.principal_id, actor="authority")
        details = {
            "mode": "embedded_core_authority",
            "reason": reason,
            "status": "revoked",
        }
        return {"ok": True, "addon_id": addon_id, "status": next_grant.status, "details": details}

    async def list_grants(self) -> list[dict[str, Any]]:
        state = await self._state_store.get_state()
        return [item.model_dump(mode="json") for item in sorted(state.active_grants.values(), key=lambda x: x.addon_id)]

    async def get_grant(self, addon_id: str) -> dict[str, Any] | None:
        state = await self._state_store.get_state()
        item = state.active_grants.get(addon_id)
        return item.model_dump(mode="json") if item is not None else None

    async def request_node_bridge_grant(
        self,
        *,
        node_id: str,
        bridge_id: str,
        bridge_type: str,
        publish_topics: list[str],
        subscribe_topics: list[str],
    ) -> dict[str, Any]:
        node_key = str(node_id or "").strip()
        bridge_key = str(bridge_id or "").strip()
        bridge_kind = str(bridge_type or "").strip() or bridge_key
        if not node_key:
            return {"ok": False, "error": "node_id_required"}
        if not bridge_key:
            return {"ok": False, "error": "bridge_id_required"}
        clean_publish = _clean_topic_list(publish_topics)
        clean_subscribe = _clean_topic_list(subscribe_topics)
        invalid_publish = _first_invalid_topic(clean_publish)
        if invalid_publish is not None:
            return {"ok": False, "error": f"topic_pattern_invalid:{invalid_publish}"}
        invalid_subscribe = _first_invalid_topic(clean_subscribe)
        if invalid_subscribe is not None:
            return {"ok": False, "error": f"topic_pattern_invalid:{invalid_subscribe}"}
        topic_errors = _bridge_topic_errors(node_id=node_key, publish_topics=clean_publish, subscribe_topics=clean_subscribe)
        if topic_errors:
            await self._append_audit(
                event_type="mqtt_topic_violation",
                status="warn",
                message="node_bridge_scope_rejected",
                payload={"node_id": node_key, "bridge_id": bridge_key, "errors": topic_errors},
            )
            return {"ok": False, "error": "node_bridge_scope_invalid", "details": topic_errors}

        grant_id = _bridge_grant_id(node_key, bridge_key)
        state = await self._state_store.get_state()
        existing = state.node_bridge_grants.get(grant_id)
        status = existing.status if existing and existing.status in {"approved", "active"} else "requested"
        grant = MqttNodeBridgeGrant(
            grant_id=grant_id,
            node_id=node_key,
            bridge_id=bridge_key,
            bridge_type=bridge_kind,
            status=status,
            requested_publish_topics=clean_publish,
            requested_subscribe_topics=clean_subscribe,
            approved_publish_topics=(existing.approved_publish_topics if existing else []),
            approved_subscribe_topics=(existing.approved_subscribe_topics if existing else []),
            requester_principal_id=f"node:{node_key}",
            bridge_principal_id=(existing.bridge_principal_id if existing else _bridge_principal_id(grant_id)),
            last_error=None,
            requested_at=(existing.requested_at if existing else _utcnow_iso()),
            approved_at=(existing.approved_at if existing else None),
            last_provisioned_at=(existing.last_provisioned_at if existing else None),
            last_revoked_at=(existing.last_revoked_at if existing else None),
        )
        await self._state_store.upsert_node_bridge_grant(grant)
        await self._append_audit(
            event_type="mqtt_node_bridge_grant_action",
            status="ok",
            message="request",
            payload={"grant_id": grant_id, "node_id": node_key, "bridge_id": bridge_key},
        )
        return {"ok": True, "grant": grant.model_dump(mode="json")}

    async def approve_node_bridge_grant(self, grant_id: str) -> dict[str, Any]:
        state = await self._state_store.get_state()
        current = state.node_bridge_grants.get(str(grant_id or "").strip())
        if current is None:
            return {"ok": False, "error": "node_bridge_grant_not_found"}
        if current.status in {"revoked", "rejected"}:
            return {"ok": False, "error": f"node_bridge_grant_{current.status}"}
        next_grant = current.model_copy(deep=True)
        next_grant.status = "approved"
        next_grant.approved_at = _utcnow_iso()
        next_grant.last_error = None
        next_grant.approved_publish_topics = _clean_topic_list(current.requested_publish_topics)
        next_grant.approved_subscribe_topics = _clean_topic_list(current.requested_subscribe_topics)
        next_grant.bridge_principal_id = next_grant.bridge_principal_id or _bridge_principal_id(next_grant.grant_id)
        await self._state_store.upsert_node_bridge_grant(next_grant)
        await self._append_audit(
            event_type="mqtt_node_bridge_grant_action",
            status="ok",
            message="approve",
            payload={"grant_id": next_grant.grant_id, "node_id": next_grant.node_id, "bridge_id": next_grant.bridge_id},
        )
        return {"ok": True, "grant": next_grant.model_dump(mode="json")}

    async def provision_node_bridge_grant(self, grant_id: str, reason: str = "api_request") -> dict[str, Any]:
        state = await self._state_store.get_state()
        current = state.node_bridge_grants.get(str(grant_id or "").strip())
        if current is None:
            return {"ok": False, "error": "node_bridge_grant_not_found"}
        if current.status not in {"approved", "active"}:
            return {"ok": False, "error": f"node_bridge_grant_not_approved:{current.status}"}
        if not self._setup_ready(state):
            next_grant = current.model_copy(deep=True)
            next_grant.status = "error"
            next_grant.last_error = f"mqtt_setup_not_ready:{state.setup_status}"
            await self._state_store.upsert_node_bridge_grant(next_grant)
            return {"ok": False, "grant_id": current.grant_id, "status": "error", "error": "mqtt_setup_not_ready"}
        next_grant = current.model_copy(deep=True)
        next_grant.status = "active"
        next_grant.last_error = None
        next_grant.last_provisioned_at = _utcnow_iso()
        next_grant.bridge_principal_id = next_grant.bridge_principal_id or _bridge_principal_id(next_grant.grant_id)
        principal = self._principal_from_node_bridge_grant(next_grant)
        principal.status = "active"
        principal.last_activated_at = _utcnow_iso()
        await self._state_store.upsert_node_bridge_grant(next_grant)
        await self._state_store.upsert_principal(principal)
        await self._reconcile_runtime_if_needed(reason=f"node_bridge_provision:{next_grant.grant_id}")
        await self._append_audit(
            event_type="mqtt_node_bridge_grant_action",
            status="ok",
            message="provision",
            payload={"grant_id": next_grant.grant_id, "reason": reason, "principal_id": principal.principal_id},
        )
        await self._append_lifecycle_audit("principal_activated", principal_id=principal.principal_id, actor="authority")
        return {"ok": True, "grant": next_grant.model_dump(mode="json"), "principal": principal.model_dump(mode="json")}

    async def claim_node_bridge_credential(
        self,
        grant_id: str,
        *,
        node_id: str,
        credential_store,
        requested_bridge_id: str | None = None,
    ) -> dict[str, Any]:
        clean_grant_id = str(grant_id or "").strip()
        clean_node_id = str(node_id or "").strip()
        clean_bridge_id = str(requested_bridge_id or "").strip()
        await self._append_audit(
            event_type="node_bridge_credential_claim_requested",
            status="ok",
            message="claim_requested",
            payload={"grant_id": clean_grant_id, "node_id": clean_node_id},
        )

        def denied(error: str, *, status_code: int = 400, extra: dict[str, Any] | None = None) -> dict[str, Any]:
            payload = {"grant_id": clean_grant_id, "node_id": clean_node_id, "error": error, **(extra or {})}
            return {"ok": False, "error": error, "status_code": status_code, "audit_payload": payload}

        async def deny(error: str, *, status_code: int = 400, extra: dict[str, Any] | None = None) -> dict[str, Any]:
            result = denied(error, status_code=status_code, extra=extra)
            await self._append_node_bridge_claim_denied(result["audit_payload"])
            return {key: value for key, value in result.items() if key != "audit_payload"}

        state = await self._state_store.get_state()
        current = state.node_bridge_grants.get(clean_grant_id)
        if current is None:
            return await deny("node_bridge_grant_not_found", status_code=404)
        if current.node_id != clean_node_id:
            return await deny("node_bridge_grant_node_mismatch", status_code=403, extra={"grant_node_id": current.node_id})
        if clean_bridge_id and current.bridge_id != clean_bridge_id:
            return await deny("node_bridge_grant_bridge_mismatch", status_code=403, extra={"grant_bridge_id": current.bridge_id})
        if current.status in {"rejected", "revoked"}:
            return await deny(f"node_bridge_grant_{current.status}", status_code=400, extra={"grant_status": current.status})
        if current.status not in {"approved", "active", "provisioned"}:
            return await deny(
                f"node_bridge_grant_not_approved:{current.status}",
                status_code=400,
                extra={"grant_status": current.status},
            )
        if credential_store is None:
            return await deny("credential_store_unavailable", status_code=503, extra={"grant_status": current.status})
        if not self._setup_ready(state):
            next_grant = current.model_copy(deep=True)
            next_grant.last_error = f"mqtt_setup_not_ready:{state.setup_status}"
            next_grant.delivery_status = "error"
            await self._state_store.upsert_node_bridge_grant(next_grant)
            return await deny("mqtt_setup_not_ready", status_code=409, extra={"setup_status": state.setup_status})

        next_grant = current.model_copy(deep=True)
        principal_id = next_grant.bridge_principal_id or _bridge_principal_id(next_grant.grant_id)
        principal = state.principals.get(principal_id)
        first_delivery = not next_grant.credential_claimed_at
        credential = credential_store.get_principal_credential(principal_id)
        should_provision = current.status == "approved" or principal is None
        if should_provision:
            next_grant.status = "active"
            next_grant.last_error = None
            next_grant.last_provisioned_at = _utcnow_iso()
            next_grant.bridge_principal_id = principal_id
            principal = self._principal_from_node_bridge_grant(next_grant)
            principal.status = "active"
            principal.last_activated_at = _utcnow_iso()
            await self._state_store.upsert_node_bridge_grant(next_grant)
            await self._state_store.upsert_principal(principal)
            state = await self._state_store.get_state()
            credential_store.render_password_file(state)
            credential = credential_store.get_principal_credential(principal_id)
            await self._reconcile_runtime_if_needed(reason=f"node_bridge_claim:{next_grant.grant_id}")
            await self._append_lifecycle_audit("principal_activated", principal_id=principal_id, actor="authority")
        elif credential is None and first_delivery:
            state = await self._state_store.get_state()
            credential_store.render_password_file(state)
            credential = credential_store.get_principal_credential(principal_id)

        if credential is None or not str(credential.get("password") or ""):
            next_grant = next_grant.model_copy(deep=True)
            next_grant.delivery_status = "error"
            next_grant.last_error = "credential_not_retrievable_rotate_required"
            await self._state_store.upsert_node_bridge_grant(next_grant)
            return await deny(
                "credential_not_retrievable_rotate_required",
                status_code=409,
                extra={"principal_id": principal_id, "grant_status": next_grant.status},
            )

        now = _utcnow_iso()
        delivered_grant = next_grant.model_copy(deep=True)
        delivered_grant.status = "active"
        delivered_grant.bridge_principal_id = principal_id
        delivered_grant.last_error = None
        delivered_grant.credential_claimed_at = delivered_grant.credential_claimed_at or now
        delivered_grant.credential_claimed_by_node_id = clean_node_id
        delivered_grant.last_credential_delivery_at = now
        delivered_grant.delivery_status = "delivered"
        await self._state_store.upsert_node_bridge_grant(delivered_grant)
        await self._append_audit(
            event_type="node_bridge_credential_claim_succeeded",
            status="ok",
            message="claim_succeeded",
            payload={"grant_id": delivered_grant.grant_id, "node_id": clean_node_id, "principal_id": principal_id},
        )
        return {
            "ok": True,
            "grant": delivered_grant.model_dump(mode="json"),
            "mqtt": {
                "username": str(credential.get("username") or ""),
                "password": str(credential.get("password") or ""),
            },
        }

    async def revoke_node_bridge_grant(self, grant_id: str, reason: str = "api_request") -> dict[str, Any]:
        state = await self._state_store.get_state()
        current = state.node_bridge_grants.get(str(grant_id or "").strip())
        if current is None:
            return {"ok": True, "grant_id": grant_id, "status": "not_found"}
        next_grant = current.model_copy(deep=True)
        next_grant.status = "revoked"
        next_grant.last_error = None
        next_grant.last_revoked_at = _utcnow_iso()
        await self._state_store.upsert_node_bridge_grant(next_grant)
        principal_id = next_grant.bridge_principal_id or _bridge_principal_id(next_grant.grant_id)
        principal = state.principals.get(principal_id)
        if principal is not None:
            next_principal = principal.model_copy(deep=True)
            next_principal.status = "revoked"
            next_principal.last_revoked_at = _utcnow_iso()
            await self._state_store.upsert_principal(next_principal)
        await self._reconcile_runtime_if_needed(reason=f"node_bridge_revoke:{next_grant.grant_id}")
        await self._append_audit(
            event_type="mqtt_node_bridge_grant_action",
            status="ok",
            message="revoke",
            payload={"grant_id": next_grant.grant_id, "reason": reason, "principal_id": principal_id},
        )
        await self._append_audit(
            event_type="node_bridge_credential_revoked",
            status="ok",
            message="credential_revoked",
            payload={"grant_id": next_grant.grant_id, "reason": reason, "principal_id": principal_id},
        )
        await self._append_lifecycle_audit("principal_revoked", principal_id=principal_id, actor="admin")
        return {"ok": True, "grant": next_grant.model_dump(mode="json")}

    async def list_node_bridge_grants(self) -> list[dict[str, Any]]:
        state = await self._state_store.get_state()
        return [item.model_dump(mode="json") for item in sorted(state.node_bridge_grants.values(), key=lambda x: x.grant_id)]

    async def get_node_bridge_grant(self, grant_id: str) -> dict[str, Any] | None:
        state = await self._state_store.get_state()
        item = state.node_bridge_grants.get(str(grant_id or "").strip())
        return item.model_dump(mode="json") if item is not None else None

    async def broker_summary(self) -> MqttBrokerModeSummary:
        state = await self._state_store.get_state()
        return MqttBrokerModeSummary(
            broker_mode=state.broker_mode,
            direct_mqtt_supported=state.direct_mqtt_supported,
        )

    async def setup_summary(self) -> MqttSetupCapabilitySummary:
        state = await self._state_store.get_state()
        return MqttSetupCapabilitySummary(
            requires_setup=state.requires_setup,
            setup_complete=state.setup_complete,
            setup_status=state.setup_status,
            direct_mqtt_supported=state.direct_mqtt_supported,
            setup_error=state.setup_error,
            authority_mode=state.authority_mode,
            authority_ready=state.authority_ready,
            runtime_ready=self._setup_ready(state),
            setup_ready=self._setup_ready(state),
        )

    async def update_setup_state(self, update: MqttSetupStateUpdate) -> MqttSetupCapabilitySummary:
        state = await self._state_store.update_setup_state(update)
        return MqttSetupCapabilitySummary(
            requires_setup=state.requires_setup,
            setup_complete=state.setup_complete,
            setup_status=state.setup_status,
            direct_mqtt_supported=state.direct_mqtt_supported,
            setup_error=state.setup_error,
            authority_mode=state.authority_mode,
            authority_ready=state.authority_ready,
            runtime_ready=self._setup_ready(state),
            setup_ready=self._setup_ready(state),
        )

    async def reconcile(self, addon_id: str) -> dict[str, Any]:
        state = await self._state_store.get_state()
        grant = state.active_grants.get(addon_id)
        if grant is None:
            if self._registry.has_addon(addon_id) and self._registry.is_enabled(addon_id):
                bootstrap = MqttAddonGrant(
                    addon_id=addon_id,
                    access_mode="gateway",
                    status="approved",
                    publish_topics=[f"hexe/addons/{addon_id}/event/#", f"hexe/addons/{addon_id}/state/#"],
                    subscribe_topics=[f"hexe/addons/{addon_id}/command/#", "hexe/bootstrap/core"],
                    granted_ha_mode="disabled",
                    access_profile="gateway",
                )
                await self._state_store.upsert_grant(bootstrap)
                await self._state_store.upsert_principal(self._principal_from_grant(bootstrap))
                await self._reconcile_runtime_if_needed(reason=f"reconcile_bootstrap:{addon_id}")
                return await self.provision_grant(addon_id, reason="onboarding_reconcile")
            return {"ok": True, "addon_id": addon_id, "status": "not_found"}
        if grant.status in {"approved", "error"} and self._registry.is_enabled(addon_id):
            return await self.provision_grant(addon_id, reason="reconcile")
        return {"ok": True, "addon_id": addon_id, "status": grant.status}

    async def list_principals(self) -> list[dict[str, Any]]:
        state = await self._state_store.get_state()
        out: list[dict[str, Any]] = []
        for item in sorted(state.principals.values(), key=lambda x: x.principal_id):
            payload = item.model_dump(mode="json")
            if not payload.get("managed_by"):
                principal_type = str(payload.get("principal_type") or "")
                payload["managed_by"] = "core" if principal_type == "system" else "authority"
            out.append(payload)
        return out

    async def get_principal(self, principal_id: str) -> dict[str, Any] | None:
        state = await self._state_store.get_state()
        item = state.principals.get(principal_id)
        return item.model_dump(mode="json") if item is not None else None

    async def apply_principal_action(self, principal_id: str, action: str, reason: str | None = None) -> dict[str, Any]:
        state = await self._state_store.get_state()
        principal = state.principals.get(principal_id)
        if principal is None:
            return {"ok": False, "error": "principal_not_found", "principal_id": principal_id}
        next_principal = principal.model_copy(deep=True)
        act = str(action).strip().lower()
        if act == "activate":
            next_principal.status = "active"
            next_principal.last_activated_at = _utcnow_iso()
            next_principal.probation_reason = None
        elif act == "revoke":
            next_principal.status = "revoked"
            next_principal.last_revoked_at = _utcnow_iso()
        elif act == "expire":
            next_principal.status = "expired"
            next_principal.expires_at = _utcnow_iso()
        elif act == "probation":
            next_principal.status = "probation"
            next_principal.probation_reason = reason or "manual_probation"
        elif act == "promote":
            next_principal.status = "active"
            next_principal.last_activated_at = _utcnow_iso()
            next_principal.probation_reason = None
        else:
            return {"ok": False, "error": "principal_action_invalid", "principal_id": principal_id}
        await self._state_store.upsert_principal(next_principal)
        await self._reconcile_runtime_if_needed(reason=f"principal_action:{act}:{principal_id}")
        await self._append_audit(
            event_type="mqtt_principal_action",
            status="ok",
            message=act,
            payload={"principal_id": principal_id, "reason": reason},
        )
        if act in {"activate", "promote"}:
            await self._append_lifecycle_audit("principal_activated", principal_id=principal_id, actor="admin")
        elif act == "revoke":
            await self._append_lifecycle_audit("principal_revoked", principal_id=principal_id, actor="admin")
        return {"ok": True, "principal": next_principal.model_dump(mode="json")}

    async def create_or_update_generic_user(
        self,
        *,
        principal_id: str,
        logical_identity: str,
        username: str | None,
        topic_prefix: str | None = None,
        access_mode: str = "private",
        allowed_topics: list[str] | None = None,
        allowed_publish_topics: list[str] | None = None,
        allowed_subscribe_topics: list[str] | None = None,
        publish_topics: list[str],
        subscribe_topics: list[str],
        approved_reserved_topics: list[str] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        invalid_publish = _first_invalid_topic(publish_topics)
        if invalid_publish is not None:
            return {"ok": False, "error": f"topic_pattern_invalid:{invalid_publish}"}
        invalid_subscribe = _first_invalid_topic(subscribe_topics)
        if invalid_subscribe is not None:
            return {"ok": False, "error": f"topic_pattern_invalid:{invalid_subscribe}"}
        invalid_allowed_publish = _first_invalid_topic(allowed_publish_topics)
        if invalid_allowed_publish is not None:
            return {"ok": False, "error": f"topic_pattern_invalid:{invalid_allowed_publish}"}
        invalid_allowed_subscribe = _first_invalid_topic(allowed_subscribe_topics)
        if invalid_allowed_subscribe is not None:
            return {"ok": False, "error": f"topic_pattern_invalid:{invalid_allowed_subscribe}"}
        policy_errors = validate_authority_topic_access(
            principal_type="generic_user",
            publish_topics=publish_topics,
            subscribe_topics=subscribe_topics,
            approved_reserved_topics=approved_reserved_topics or [],
        )
        if policy_errors:
            await self._append_audit(
                event_type="mqtt_topic_violation",
                status="warn",
                message="generic_scope_rejected",
                payload={"principal_id": principal_id, "errors": policy_errors},
            )
            return {"ok": False, "error": "generic_user_scope_invalid", "details": policy_errors}
        state = await self._state_store.get_state()
        existing = state.principals.get(principal_id)
        principal = (existing.model_copy(deep=True) if existing else MqttPrincipal(
            principal_id=principal_id,
            principal_type="generic_user",
            status="active",
            logical_identity=logical_identity,
        ))
        principal.principal_type = "generic_user"
        principal.logical_identity = logical_identity
        principal.username = username or principal.username
        if topic_prefix is not None:
            principal.topic_prefix = topic_prefix
        principal.access_mode = str(access_mode or "private")
        normalized_allowed_topics = sorted({str(topic).strip() for topic in (allowed_topics or []) if str(topic).strip()})
        normalized_allowed_publish_topics = sorted(
            {str(topic).strip() for topic in (allowed_publish_topics or []) if str(topic).strip()}
        )
        normalized_allowed_subscribe_topics = sorted(
            {str(topic).strip() for topic in (allowed_subscribe_topics or []) if str(topic).strip()}
        )
        if not normalized_allowed_publish_topics and normalized_allowed_topics:
            normalized_allowed_publish_topics = list(normalized_allowed_topics)
        if not normalized_allowed_subscribe_topics and normalized_allowed_topics:
            normalized_allowed_subscribe_topics = list(normalized_allowed_topics)
        principal.allowed_publish_topics = normalized_allowed_publish_topics
        principal.allowed_subscribe_topics = normalized_allowed_subscribe_topics
        principal.allowed_topics = sorted({*normalized_allowed_publish_topics, *normalized_allowed_subscribe_topics})
        principal.publish_topics = sorted({topic for topic in publish_topics if topic and not is_platform_reserved_topic(topic)})
        principal.subscribe_topics = sorted({topic for topic in subscribe_topics if topic and not is_platform_reserved_topic(topic)})
        principal.approved_reserved_topics = []
        if principal.status in {"revoked", "expired"}:
            principal.status = "active"
        if notes is not None:
            principal.notes = notes
        principal.managed_by = principal.managed_by or "operator"
        principal.last_activated_at = principal.last_activated_at or _utcnow_iso()
        await self._state_store.upsert_principal(principal)
        await self._reconcile_runtime_if_needed(reason=f"generic_user_update:{principal_id}")
        await self._append_audit(
            event_type="mqtt_generic_user_action",
            status="ok",
            message="upsert",
            payload={"principal_id": principal_id},
        )
        if existing is None:
            await self._append_lifecycle_audit("principal_created", principal_id=principal_id, actor="operator")
        if principal.status == "active":
            await self._append_lifecycle_audit("principal_activated", principal_id=principal_id, actor="operator")
        return {"ok": True, "principal": principal.model_dump(mode="json")}

    async def update_generic_user_topic_prefix(
        self,
        *,
        principal_id: str,
        topic_prefix: str,
        access_mode: str | None = None,
        allowed_topics: list[str] | None = None,
        allowed_publish_topics: list[str] | None = None,
        allowed_subscribe_topics: list[str] | None = None,
    ) -> dict[str, Any]:
        state = await self._state_store.get_state()
        current = state.principals.get(principal_id)
        if current is None:
            return {"ok": False, "error": "principal_not_found"}
        if current.principal_type != "generic_user":
            return {"ok": False, "error": "principal_type_invalid"}
        prefix = str(topic_prefix or "").strip().strip("/")
        mode = str(access_mode or current.access_mode or "private").strip().lower()
        if mode not in {"private", "custom", "non_reserved", "admin"}:
            return {"ok": False, "error": "access_mode_invalid"}
        if mode == "private":
            if not prefix:
                return {"ok": False, "error": "topic_prefix_required"}
            publish_topics = [f"{prefix}/#"]
            subscribe_topics = [f"{prefix}/#"]
            custom_topics: list[str] = []
            custom_publish_topics: list[str] = []
            custom_subscribe_topics: list[str] = []
        elif mode == "custom":
            fallback_topics = sorted({str(topic).strip() for topic in (allowed_topics or current.allowed_topics) if str(topic).strip()})
            custom_publish_topics = sorted(
                {
                    str(topic).strip()
                    for topic in (allowed_publish_topics or current.allowed_publish_topics or fallback_topics)
                    if str(topic).strip()
                }
            )
            custom_subscribe_topics = sorted(
                {
                    str(topic).strip()
                    for topic in (allowed_subscribe_topics or current.allowed_subscribe_topics or fallback_topics)
                    if str(topic).strip()
                }
            )
            if not custom_publish_topics or not custom_subscribe_topics:
                return {"ok": False, "error": "allowed_topics_required"}
            if not prefix:
                prefix = current.topic_prefix or ""
            publish_topics = list(custom_publish_topics)
            subscribe_topics = list(custom_subscribe_topics)
            custom_topics = sorted({*custom_publish_topics, *custom_subscribe_topics})
        else:
            publish_topics = ["#"]
            subscribe_topics = ["#"]
            if not prefix:
                prefix = current.topic_prefix or ""
            custom_topics = []
            custom_publish_topics = []
            custom_subscribe_topics = []
        result = await self.create_or_update_generic_user(
            principal_id=principal_id,
            logical_identity=current.logical_identity,
            username=current.username,
            topic_prefix=prefix,
            access_mode=mode,
            allowed_topics=(custom_topics if mode == "custom" else []),
            allowed_publish_topics=(custom_publish_topics if mode == "custom" else []),
            allowed_subscribe_topics=(custom_subscribe_topics if mode == "custom" else []),
            publish_topics=publish_topics,
            subscribe_topics=subscribe_topics,
            notes=current.notes,
        )
        if result.get("ok"):
            await self._append_audit(
                event_type="mqtt_generic_user_action",
                status="ok",
                message="edit",
                payload={"principal_id": principal_id, "topic_prefix": prefix, "access_mode": mode},
            )
        return result

    async def delete_generic_user(self, principal_id: str) -> dict[str, Any]:
        state = await self._state_store.get_state()
        current = state.principals.get(principal_id)
        if current is None:
            return {"ok": False, "error": "principal_not_found"}
        if current.principal_type != "generic_user":
            return {"ok": False, "error": "principal_type_invalid"}
        await self._state_store.remove_principal(principal_id)
        if callable(self._credential_rotate_hook):
            try:
                self._credential_rotate_hook(principal_id)
            except Exception:
                pass
        await self._reconcile_runtime_if_needed(reason=f"generic_user_delete:{principal_id}")
        await self._append_audit(
            event_type="mqtt_generic_user_action",
            status="ok",
            message="delete",
            payload={"principal_id": principal_id},
        )
        await self._append_lifecycle_audit("principal_revoked", principal_id=principal_id, actor="operator")
        return {"ok": True, "principal_id": principal_id}

    async def list_noisy_clients(self) -> list[dict[str, Any]]:
        principals = await self.list_principals()
        out: list[dict[str, Any]] = []
        for item in principals:
            noisy_state = str(item.get("noisy_state") or "normal")
            if noisy_state != "normal":
                out.append(item)
        return out

    async def apply_noisy_client_action(self, principal_id: str, action: str, reason: str | None = None) -> dict[str, Any]:
        state = await self._state_store.get_state()
        principal = state.principals.get(principal_id)
        if principal is None:
            return {"ok": False, "error": "principal_not_found", "principal_id": principal_id}
        act = str(action).strip().lower()
        next_principal = principal.model_copy(deep=True)
        if act in {"mark_watch", "watch"}:
            next_principal.noisy_state = "watch"
        elif act in {"mark_noisy", "noisy"}:
            next_principal.noisy_state = "noisy"
        elif act in {"quarantine", "block"}:
            next_principal.noisy_state = "blocked"
            if act == "quarantine":
                next_principal.status = "probation"
                next_principal.probation_reason = reason or "quarantined_by_admin"
            else:
                next_principal.status = "revoked"
                next_principal.last_revoked_at = _utcnow_iso()
        elif act in {"throttle"}:
            next_principal.noisy_state = "noisy"
            next_principal.status = "probation"
            next_principal.probation_reason = reason or "throttled_by_admin"
        elif act in {"clear", "clear_noisy"}:
            next_principal.noisy_state = "normal"
            next_principal.noisy_inputs = {}
            if next_principal.status == "probation":
                next_principal.status = "active"
                next_principal.probation_reason = None
        elif act in {"revoke_credentials", "rotate_credentials"}:
            rotated = False
            if callable(self._credential_rotate_hook):
                try:
                    rotated = bool(self._credential_rotate_hook(principal_id))
                except Exception:
                    rotated = False
            next_principal.noisy_updated_at = _utcnow_iso()
            await self._state_store.upsert_principal(next_principal)
            await self._reconcile_runtime_if_needed(reason=f"noisy_action:{act}:{principal_id}")
            await self._append_audit(
                event_type="mqtt_noisy_client_action",
                status="ok",
                message=act,
                payload={"principal_id": principal_id, "reason": reason, "rotated": rotated},
            )
            if act in {"revoke_credentials", "rotate_credentials"} and rotated:
                await self._append_lifecycle_audit("password_rotated", principal_id=principal_id, actor="admin")
                if principal.managed_by == "node_bridge_grant":
                    bridge_grant = next(
                        (
                            grant
                            for grant in state.node_bridge_grants.values()
                            if (grant.bridge_principal_id or _bridge_principal_id(grant.grant_id)) == principal_id
                        ),
                        None,
                    )
                    await self._append_audit(
                        event_type=(
                            "node_bridge_credential_rotated"
                            if act == "rotate_credentials"
                            else "node_bridge_credential_revoked"
                        ),
                        status="ok",
                        message=("credential_rotated" if act == "rotate_credentials" else "credential_revoked"),
                        payload={
                            "grant_id": bridge_grant.grant_id if bridge_grant else None,
                            "node_id": bridge_grant.node_id if bridge_grant else principal.linked_node_id,
                            "principal_id": principal_id,
                            "reason": reason,
                        },
                    )
            return {"ok": True, "principal": next_principal.model_dump(mode="json"), "rotated": rotated}
        else:
            return {"ok": False, "error": "noisy_action_invalid", "principal_id": principal_id}
        next_principal.noisy_updated_at = _utcnow_iso()
        await self._state_store.upsert_principal(next_principal)
        await self._reconcile_runtime_if_needed(reason=f"noisy_action:{act}:{principal_id}")
        await self._append_audit(
            event_type="mqtt_noisy_client_action",
            status="ok",
            message=act,
            payload={"principal_id": principal_id, "reason": reason},
        )
        return {"ok": True, "principal": next_principal.model_dump(mode="json")}

    def _grant_materially_changed(self, old: MqttAddonGrant, new: MqttAddonGrant) -> bool:
        if old.access_mode != new.access_mode:
            return True
        if sorted(old.publish_topics) != sorted(new.publish_topics):
            return True
        if sorted(old.subscribe_topics) != sorted(new.subscribe_topics):
            return True
        if old.granted_ha_mode != new.granted_ha_mode:
            return True
        return False

    def _setup_ready(self, state) -> bool:
        if not state.mqtt_enabled:
            return False
        if state.requires_setup:
            return state.setup_complete and state.setup_status == "ready" and state.authority_ready
        return state.authority_ready

    def _principal_from_grant(self, grant: MqttAddonGrant) -> MqttPrincipal:
        approved_reserved_topics = [
            topic for topic in list(grant.publish_topics) + list(grant.subscribe_topics) if is_platform_reserved_topic(topic)
        ]
        return MqttPrincipal(
            principal_id=f"addon:{grant.addon_id}",
            principal_type="synthia_addon",
            status=("active" if grant.status == "active" else "pending"),
            logical_identity=grant.addon_id,
            linked_addon_id=grant.addon_id,
            managed_by="authority",
            publish_topics=sorted({str(topic).strip() for topic in grant.publish_topics if str(topic).strip()}),
            subscribe_topics=sorted({str(topic).strip() for topic in grant.subscribe_topics if str(topic).strip()}),
            approved_reserved_topics=sorted({str(topic).strip() for topic in approved_reserved_topics if str(topic).strip()}),
            notes=f"created_from_grant:{grant.access_mode}",
        )

    @staticmethod
    def _principal_from_node_bridge_grant(grant: MqttNodeBridgeGrant) -> MqttPrincipal:
        publish_topics = _clean_topic_list(grant.approved_publish_topics or grant.requested_publish_topics)
        subscribe_topics = _clean_topic_list(grant.approved_subscribe_topics or grant.requested_subscribe_topics)
        principal_id = grant.bridge_principal_id or _bridge_principal_id(grant.grant_id)
        return MqttPrincipal(
            principal_id=principal_id,
            principal_type="generic_user",
            status=("active" if grant.status == "active" else "pending"),
            logical_identity=f"node_bridge:{grant.grant_id}",
            linked_node_id=grant.node_id,
            username=_bridge_username(grant.node_id, grant.bridge_id),
            topic_prefix=f"bridges/{grant.node_id}/{grant.bridge_id}",
            access_mode="custom",
            allowed_topics=sorted({*publish_topics, *subscribe_topics}),
            allowed_publish_topics=publish_topics,
            allowed_subscribe_topics=subscribe_topics,
            publish_topics=publish_topics,
            subscribe_topics=subscribe_topics,
            managed_by="node_bridge_grant",
            notes=f"Node bridge MQTT grant {grant.grant_id}",
        )

    async def _record_observability(self, *, event_type: str, severity: str, metadata: dict[str, Any]) -> None:
        if self._observability is None:
            return
        try:
            await self._observability.append_event(
                event_type=event_type,
                source="mqtt_approval",
                severity=severity,
                metadata=metadata,
            )
        except Exception:
            return

    async def _reconcile_runtime_if_needed(self, *, reason: str) -> None:
        if self._runtime_reconcile_hook is None:
            return
        try:
            await self._runtime_reconcile_hook(reason=reason)
        except Exception:
            await self._record_observability(
                event_type="broker_readiness_issue",
                severity="warn",
                metadata={"reason": reason, "error": "runtime_reconcile_failed"},
            )

    async def _append_audit(self, *, event_type: str, status: str, message: str, payload: dict[str, Any]) -> None:
        if self._audit is None:
            return
        try:
            await self._audit.append_event(event_type=event_type, status=status, message=message, payload=payload)
        except Exception:
            return

    async def _append_node_bridge_claim_denied(self, payload: dict[str, Any]) -> None:
        payload = {key: value for key, value in payload.items() if key != "password"}
        await self._append_audit(
            event_type="node_bridge_credential_claim_denied",
            status="denied",
            message=str(payload.get("error") or "claim_denied"),
            payload=payload,
        )

    async def _append_lifecycle_audit(self, action: str, *, principal_id: str, actor: str) -> None:
        await self._append_audit(
            event_type=action,
            status="ok",
            message=action,
            payload={
                "actor": actor,
                "principal_id": principal_id,
                "action": action,
            },
        )
