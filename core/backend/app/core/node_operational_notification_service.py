from __future__ import annotations

import logging
import os
import time
from typing import Any

from app.system.onboarding import NodeGovernanceStatusService, NodeRegistrationsStore, node_registry_payload
from .notification_publisher import CoreNotificationPublisher


def _node_status_stale_after_s() -> int:
    raw = str(os.getenv("SYNTHIA_NODE_STATUS_STALE_AFTER_S", "300")).strip()
    try:
        return max(30, int(raw))
    except Exception:
        return 300


def _node_status_inactive_after_s() -> int:
    raw = str(os.getenv("SYNTHIA_NODE_STATUS_INACTIVE_AFTER_S", "1800")).strip()
    try:
        inactive_after = max(60, int(raw))
    except Exception:
        inactive_after = 1800
    return max(inactive_after, _node_status_stale_after_s() + 1)


class NodeOperationalNotificationService:
    def __init__(
        self,
        publisher: CoreNotificationPublisher,
        mqtt_manager,
        registrations_store: NodeRegistrationsStore,
        node_governance_status_service: NodeGovernanceStatusService | None = None,
    ) -> None:
        self._publisher = publisher
        self._mqtt = mqtt_manager
        self._registrations = registrations_store
        self._governance = node_governance_status_service
        self._log = logging.getLogger("synthia.core.notifications")
        self._last_health_by_node: dict[str, str] = {}

    async def poll_once(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        current_nodes: set[str] = set()
        for registration in self._registrations.list():
            node_id = str(getattr(registration, "node_id", "") or "").strip()
            if not node_id:
                continue
            current_nodes.add(node_id)
            if str(getattr(registration, "trust_status", "") or "").strip().lower() != "trusted":
                self._last_health_by_node.pop(node_id, None)
                continue

            node_payload = node_registry_payload(registration, self._governance)
            if not bool(node_payload.get("operational_ready")):
                self._last_health_by_node.pop(node_id, None)
                continue

            status = await self._effective_health_status(node_id)
            if status not in {"offline", "degraded"}:
                self._last_health_by_node[node_id] = status
                continue

            previous = self._last_health_by_node.get(node_id)
            self._last_health_by_node[node_id] = status
            if previous == status:
                continue

            result = await self._emit_warning(
                node_id=node_id,
                node_name=str(node_payload.get("node_name") or node_id),
                status=status,
            )
            results.append(result)

        for node_id in list(self._last_health_by_node.keys()):
            if node_id not in current_nodes:
                self._last_health_by_node.pop(node_id, None)
        return results

    async def _effective_health_status(self, node_id: str) -> str | None:
        snapshot_fn = getattr(self._mqtt, "node_runtime_snapshot", None)
        if not callable(snapshot_fn):
            return None
        snapshot = await snapshot_fn(node_id)
        if not isinstance(snapshot, dict):
            return None
        effective_health_status = str(snapshot.get("reported_health_status") or "").strip().lower() or None
        status_reported_epoch = float(snapshot.get("_last_status_report_epoch") or 0.0)
        if status_reported_epoch > 0.0:
            last_status_age_s = max(0, int(time.time() - status_reported_epoch))
            if last_status_age_s > _node_status_inactive_after_s():
                return "offline"
            if last_status_age_s > _node_status_stale_after_s():
                return "degraded"
        return effective_health_status

    async def _emit_warning(self, *, node_id: str, node_name: str, status: str) -> dict[str, Any]:
        health_label = "Offline" if status == "offline" else "Degraded"
        message = f"Installed node {node_name} ({node_id}) is {status}."
        payload = {
            "source": {
                "kind": "core",
                "id": "hexe-core",
                "component": "node_operational_monitor",
            },
            "targets": {
                "broadcast": True,
                "external": ["ha"],
            },
            "delivery": {
                "severity": "warning",
                "priority": "high",
                "urgency": "actions_needed",
                "channels": ["popup", "event"],
                "ttl_seconds": 900,
                "dedupe_key": f"node-{node_id}-{status}",
            },
            "content": {
                "title": f"Node {health_label}",
                "message": message,
            },
            "event": {
                "event_type": "node_operational_warning",
                "action": status,
                "summary": message,
                "attributes": {"node_id": node_id, "node_name": node_name, "health_status": status},
            },
            "data": {
                "node_id": node_id,
                "node_name": node_name,
                "health_status": status,
            },
        }
        popup_result = await self._publisher.publish_internal_popup(payload)
        event_result = await self._publisher.publish_internal_event(payload)
        result = {
            "ok": bool(popup_result.get("ok")) and bool(event_result.get("ok")),
            "node_id": node_id,
            "status": status,
            "popup_topic": popup_result.get("topic"),
            "event_topic": event_result.get("topic"),
        }
        self._log.info(
            "node_operational_notification_emitted node_id=%s status=%s popup_ok=%s event_ok=%s",
            node_id,
            status,
            bool(popup_result.get("ok")),
            bool(event_result.get("ok")),
        )
        return result
