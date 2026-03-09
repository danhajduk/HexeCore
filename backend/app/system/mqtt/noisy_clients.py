from __future__ import annotations

from datetime import datetime, timezone

from .integration_state import MqttIntegrationStateStore


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MqttNoisyClientEvaluator:
    def __init__(self, *, state_store: MqttIntegrationStateStore, mqtt_manager, observability_store=None, audit_store=None) -> None:
        self._state_store = state_store
        self._mqtt = mqtt_manager
        self._observability = observability_store
        self._audit = audit_store

    async def evaluate(self) -> dict[str, object]:
        state = await self._state_store.get_state()
        status = await self._mqtt.status()
        reconnect_spikes = int(status.get("reconnect_spikes") or 0)
        auth_failures = int(status.get("auth_failures") or 0)
        connection_churn = int(status.get("connection_count") or 0)

        changed: list[str] = []
        for principal in sorted(state.principals.values(), key=lambda item: item.principal_id):
            if principal.noisy_state == "blocked":
                continue
            denied = await self._denied_topic_attempts_for_principal(principal.principal_id, principal.linked_addon_id)
            inputs = {
                "reconnect_spikes": reconnect_spikes,
                "auth_failures": auth_failures,
                "connection_churn": connection_churn,
                "denied_topic_attempts": denied,
            }
            next_state = self._score_state(inputs)
            if principal.noisy_state != next_state or principal.noisy_inputs != inputs:
                principal.noisy_state = next_state
                principal.noisy_inputs = inputs
                principal.noisy_updated_at = _utcnow_iso()
                await self._state_store.upsert_principal(principal)
                changed.append(principal.principal_id)

        if changed and self._audit is not None:
            try:
                await self._audit.append_event(
                    event_type="mqtt_noisy_evaluation",
                    status="ok",
                    message="state_updated",
                    payload={"principals": changed},
                )
            except Exception:
                pass
        return {"ok": True, "updated_principals": changed}

    async def _denied_topic_attempts_for_principal(self, principal_id: str, linked_addon_id: str | None) -> int:
        if self._observability is None:
            return 0
        if linked_addon_id:
            return int(
                await self._observability.count_events(
                    event_type="denied_topic_attempt",
                    metadata_contains={"addon_id": linked_addon_id},
                )
            )
        return int(
            await self._observability.count_events(
                event_type="denied_topic_attempt",
                metadata_contains={"principal_id": principal_id},
            )
        )

    @staticmethod
    def _score_state(inputs: dict[str, int]) -> str:
        score = 0
        if int(inputs.get("reconnect_spikes") or 0) >= 5:
            score += 1
        if int(inputs.get("auth_failures") or 0) >= 5:
            score += 1
        if int(inputs.get("denied_topic_attempts") or 0) >= 3:
            score += 1
        if int(inputs.get("connection_churn") or 0) >= 20:
            score += 1
        if score >= 2:
            return "noisy"
        if score == 1:
            return "watch"
        return "normal"
