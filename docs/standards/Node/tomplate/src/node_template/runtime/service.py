from node_template.config.settings import Settings


class NodeRuntimeService:
    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings

    def status_payload(self) -> dict:
        return {
            "node_name": self._settings.node_name,
            "node_type": self._settings.node_type,
            "node_id": None,
            "lifecycle_state": "unconfigured",
            "trust_state": "untrusted",
            "operational_ready": False,
            "blocking_reasons": ["not_onboarded"],
        }
