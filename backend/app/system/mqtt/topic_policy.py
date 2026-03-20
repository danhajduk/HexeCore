from __future__ import annotations

from typing import Iterable

from .authority_policy import validate_authority_topic_access
from .topic_families import MQTT_TOPIC_ROOT, is_addon_scoped_topic, is_hexe_topic, is_platform_reserved_topic, normalize_topic


def validate_topic_scopes(
    addon_id: str,
    publish_topics: Iterable[str],
    subscribe_topics: Iterable[str],
    *,
    approved_reserved_topics: Iterable[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    for raw in publish_topics:
        topic = normalize_topic(raw)
        if not topic:
            errors.append("publish topic is empty")
            continue
        if not is_hexe_topic(topic):
            errors.append(f"publish topic '{topic}' must start with '{MQTT_TOPIC_ROOT}/'")
            continue
        if is_platform_reserved_topic(topic):
            continue
        if not is_addon_scoped_topic(topic, addon_id=addon_id):
            errors.append(f"publish topic '{topic}' must remain under {MQTT_TOPIC_ROOT}/addons/{addon_id}/...")

    for raw in subscribe_topics:
        topic = normalize_topic(raw)
        if not topic:
            errors.append("subscribe topic is empty")
            continue
        if not is_hexe_topic(topic):
            errors.append(f"subscribe topic '{topic}' must start with '{MQTT_TOPIC_ROOT}/'")
            continue
        if is_addon_scoped_topic(topic, addon_id=addon_id) or is_platform_reserved_topic(topic):
            continue
        errors.append(f"subscribe topic '{topic}' is outside allowed namespaces")
    policy_errors = validate_authority_topic_access(
        principal_type="synthia_addon",
        publish_topics=publish_topics,
        subscribe_topics=subscribe_topics,
        approved_reserved_topics=approved_reserved_topics,
    )
    errors.extend(policy_errors)
    return sorted(set(errors))
