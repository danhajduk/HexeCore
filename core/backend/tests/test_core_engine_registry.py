import pytest

from app.engines import CoreEngineRegistration, CoreEngineRegistry, CoreEngineRegistryError


def registration(engine_id: str, owns: str, *dependencies: str) -> CoreEngineRegistration:
    return CoreEngineRegistration(engine_id=engine_id, owns=(owns,), dependencies=dependencies)


def test_registry_validates_and_returns_redacted_topology() -> None:
    registry = CoreEngineRegistry()
    registry.register(registration("identity-access", "users-sessions-devices"))
    registry.register(registration("people-household", "people-consent", "identity-access"))
    snapshot = registry.snapshot()
    assert [item["engine_id"] for item in snapshot] == ["identity-access", "people-household"]
    assert set(snapshot[1]) == {"engine_id", "owns", "dependencies", "required"}


@pytest.mark.parametrize("registrations,error", [
    ([registration("identity", "users"), registration("identity", "devices")], "core_engine_duplicate"),
    ([registration("identity", "users"), registration("people", "users")], "core_engine_ownership_conflict"),
    ([registration("people", "people", "identity")], "core_engine_dependency_missing:identity"),
    ([registration("identity", "users", "people"), registration("people", "people", "identity")], "core_engine_dependency_cycle"),
])
def test_registry_rejects_invalid_topologies(registrations, error) -> None:
    registry = CoreEngineRegistry()
    with pytest.raises(CoreEngineRegistryError, match=error):
        for item in registrations:
            registry.register(item)
        registry.validate()
