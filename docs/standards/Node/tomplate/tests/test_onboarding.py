from node_template.runtime.service import NodeRuntimeService
from node_template.config.settings import Settings


def test_initial_state_is_unconfigured():
    service = NodeRuntimeService(settings=Settings())
    assert service.status_payload()["lifecycle_state"] == "unconfigured"
