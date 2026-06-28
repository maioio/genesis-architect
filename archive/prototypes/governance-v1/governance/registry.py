"""Engine registry. Engines register specs here; the orchestrator queries by
phase/tier. Adding an engine never requires editing the orchestrator or the
Decision Engine - that is the modularity contract."""

from __future__ import annotations

from genesis_architect_pro.governance.contracts import EngineSpec


class EngineRegistry:
    """A simple, deterministic registry of EngineSpecs."""

    def __init__(self) -> None:
        self._specs: dict[str, EngineSpec] = {}

    def register(self, spec: EngineSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"engine already registered: {spec.name}")
        self._specs[spec.name] = spec

    def unregister(self, name: str) -> None:
        self._specs.pop(name, None)

    def get(self, name: str) -> EngineSpec | None:
        return self._specs.get(name)

    def all(self) -> list[EngineSpec]:
        return list(self._specs.values())

    def for_phase(self, phase_value: str) -> list[EngineSpec]:
        """Engines that participate in a given lifecycle phase."""
        return [s for s in self._specs.values() if phase_value in s.phases]

    def by_tier(self, tier: str) -> list[EngineSpec]:
        return [s for s in self._specs.values() if s.tier == tier]

    def __len__(self) -> int:
        return len(self._specs)

    def __contains__(self, name: str) -> bool:
        return name in self._specs
