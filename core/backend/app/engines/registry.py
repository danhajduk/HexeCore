from __future__ import annotations

from dataclasses import dataclass


class CoreEngineRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class CoreEngineRegistration:
    engine_id: str
    owns: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    required: bool = True

    def __post_init__(self) -> None:
        if not self.engine_id or not self.engine_id.replace("-", "").isalnum():
            raise CoreEngineRegistryError("core_engine_id_invalid")
        if not self.owns or any(not item.strip() for item in self.owns):
            raise CoreEngineRegistryError("core_engine_ownership_invalid")
        if self.engine_id in self.dependencies:
            raise CoreEngineRegistryError("core_engine_self_dependency")


class CoreEngineRegistry:
    """In-process ownership topology for required Core trust-boundary engines."""

    def __init__(self) -> None:
        self._engines: dict[str, CoreEngineRegistration] = {}

    def register(self, registration: CoreEngineRegistration) -> None:
        if registration.engine_id in self._engines:
            raise CoreEngineRegistryError("core_engine_duplicate")
        claimed = {owned for engine in self._engines.values() for owned in engine.owns}
        if claimed.intersection(registration.owns):
            raise CoreEngineRegistryError("core_engine_ownership_conflict")
        self._engines[registration.engine_id] = registration

    def validate(self) -> None:
        known = set(self._engines)
        if missing := {dependency for engine in self._engines.values() for dependency in engine.dependencies if dependency not in known}:
            raise CoreEngineRegistryError(f"core_engine_dependency_missing:{','.join(sorted(missing))}")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(engine_id: str) -> None:
            if engine_id in visiting:
                raise CoreEngineRegistryError("core_engine_dependency_cycle")
            if engine_id in visited:
                return
            visiting.add(engine_id)
            for dependency in self._engines[engine_id].dependencies:
                visit(dependency)
            visiting.remove(engine_id)
            visited.add(engine_id)

        for engine_id in sorted(known):
            visit(engine_id)

    def snapshot(self) -> tuple[dict[str, object], ...]:
        self.validate()
        return tuple(
            {
                "engine_id": engine.engine_id,
                "owns": list(engine.owns),
                "dependencies": list(engine.dependencies),
                "required": engine.required,
            }
            for engine in sorted(self._engines.values(), key=lambda item: item.engine_id)
        )
