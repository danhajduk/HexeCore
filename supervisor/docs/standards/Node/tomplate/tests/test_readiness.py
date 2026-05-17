from node_template.runtime.service import NodeRuntimeService
from node_template.config.settings import Settings


def test_initial_state_not_ready():
    service = NodeRuntimeService(settings=Settings())
    assert service.status_payload()["operational_ready"] is False
