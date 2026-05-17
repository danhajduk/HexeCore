from node_template.runtime.service import NodeRuntimeService
from node_template.config.settings import Settings


def test_template_starts_without_scheduler_requirements():
    service = NodeRuntimeService(settings=Settings())
    assert "not_onboarded" in service.status_payload()["blocking_reasons"]
