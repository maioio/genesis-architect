"""Genesis Decision Engine — engine registry.

Stores EngineDescriptor registrations and provides:
- Registration with validation
- Lookup by ID and by mode
- Topological sort (dependency ordering)
- Duplicate and cycle detection

No engine logic or imports from individual engine modules live here.
"""

from __future__ import annotations

from collections import defaultdict, deque

from genesis_architect_pro.gde_types import EngineDescriptor, GDEMode


class RegistryError(Exception):
    """Raised when the registry is in an invalid state."""


class EngineRegistry:
    """Central store of all EngineDescriptor registrations.

    Usage::

        registry = EngineRegistry()
        registry.register(descriptor)
        ordered = registry.ordered_for_mode(GDEMode.RECOVERY)
    """

    def __init__(self) -> None:
        self._descriptors: dict[str, EngineDescriptor] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, descriptor: EngineDescriptor) -> None:
        """Register one engine descriptor.

        Raises RegistryError if the ID is already registered or if any
        declared dependency ID does not exist at validation time.
        """
        if not isinstance(descriptor, EngineDescriptor):
            raise TypeError(f"Expected EngineDescriptor, got {type(descriptor)}")
        if descriptor.id in self._descriptors:
            raise RegistryError(
                f"Engine '{descriptor.id}' is already registered. "
                "Use replace() to overwrite."
            )
        self._descriptors[descriptor.id] = descriptor

    def replace(self, descriptor: EngineDescriptor) -> None:
        """Register or overwrite an engine descriptor."""
        if not isinstance(descriptor, EngineDescriptor):
            raise TypeError(f"Expected EngineDescriptor, got {type(descriptor)}")
        self._descriptors[descriptor.id] = descriptor

    def unregister(self, engine_id: str) -> None:
        """Remove an engine from the registry. Silently does nothing if absent."""
        self._descriptors.pop(engine_id, None)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, engine_id: str) -> EngineDescriptor | None:
        """Return the descriptor for engine_id, or None if not registered."""
        return self._descriptors.get(engine_id)

    def require(self, engine_id: str) -> EngineDescriptor:
        """Return the descriptor for engine_id, raising RegistryError if absent."""
        desc = self._descriptors.get(engine_id)
        if desc is None:
            raise RegistryError(f"Engine '{engine_id}' is not registered.")
        return desc

    def all(self) -> list[EngineDescriptor]:
        """Return all registered descriptors in insertion order."""
        return list(self._descriptors.values())

    def for_mode(self, mode: GDEMode) -> list[EngineDescriptor]:
        """Return all descriptors that declare they run in the given mode."""
        return [d for d in self._descriptors.values() if mode in d.modes]

    def ids(self) -> list[str]:
        """Return all registered engine IDs in insertion order."""
        return list(self._descriptors.keys())

    def __len__(self) -> int:
        return len(self._descriptors)

    def __contains__(self, engine_id: str) -> bool:
        return engine_id in self._descriptors

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Check the registry for structural errors.

        Returns a list of error strings. An empty list means the registry
        is valid. Does NOT raise — callers decide how to handle errors.
        """
        errors: list[str] = []

        for desc in self._descriptors.values():
            # Dependency existence check
            for dep_id in desc.requires:
                if dep_id not in self._descriptors:
                    errors.append(
                        f"Engine '{desc.id}' requires '{dep_id}' which is not registered."
                    )

        # Cycle detection via Kahn's algorithm
        cycle_errors = self._detect_cycles()
        errors.extend(cycle_errors)

        return errors

    def validate_strict(self) -> None:
        """Like validate(), but raises RegistryError on the first error found."""
        errors = self.validate()
        if errors:
            raise RegistryError(errors[0])

    def _detect_cycles(self) -> list[str]:
        """Return error strings for any dependency cycles detected."""
        # Build adjacency list: engine_id → set of its dependencies
        graph: dict[str, set[str]] = {
            d.id: set(r for r in d.requires if r in self._descriptors)
            for d in self._descriptors.values()
        }

        # Kahn's algorithm: track in-degree and process zero-in-degree nodes
        in_degree: dict[str, int] = defaultdict(int)
        for deps in graph.values():
            for dep in deps:
                in_degree[dep] += 1  # dep is depended-upon, not the depender

        # Correct direction: for topological sort, edges go dep → dependant
        # Rebuild: dependant has edges from its requires
        forward: dict[str, list[str]] = defaultdict(list)
        in_deg2: dict[str, int] = {d.id: 0 for d in self._descriptors.values()}
        for desc in self._descriptors.values():
            for dep_id in desc.requires:
                if dep_id in self._descriptors:
                    forward[dep_id].append(desc.id)
                    in_deg2[desc.id] += 1

        queue: deque[str] = deque(e for e, d in in_deg2.items() if d == 0)
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for dependant in forward[node]:
                in_deg2[dependant] -= 1
                if in_deg2[dependant] == 0:
                    queue.append(dependant)

        if visited < len(self._descriptors):
            # Nodes not visited are part of a cycle
            cycle_members = [e for e, d in in_deg2.items() if d > 0]
            return [
                f"Dependency cycle detected among engines: {cycle_members}"
            ]
        return []

    # ------------------------------------------------------------------
    # Topological sort
    # ------------------------------------------------------------------

    def ordered_for_mode(self, mode: GDEMode) -> list[EngineDescriptor]:
        """Return descriptors for a mode in topologically sorted order.

        Engines are sorted so that if engine B requires engine A, A appears
        before B in the result. Raises RegistryError if a cycle exists among
        the mode's engines.

        Only engines that declare the given mode are included. Dependencies
        that are not in the mode's set are ignored for ordering purposes
        (they may belong to a different mode or be pre-conditions fulfilled
        elsewhere).
        """
        mode_engines = {d.id: d for d in self.for_mode(mode)}
        if not mode_engines:
            return []

        # Build in-degree map restricted to this mode's engines
        in_deg: dict[str, int] = {eid: 0 for eid in mode_engines}
        forward: dict[str, list[str]] = defaultdict(list)

        for desc in mode_engines.values():
            for dep_id in desc.requires:
                if dep_id in mode_engines:
                    forward[dep_id].append(desc.id)
                    in_deg[desc.id] += 1

        queue: deque[str] = deque(e for e, d in in_deg.items() if d == 0)
        result: list[EngineDescriptor] = []

        while queue:
            # Stable sort within zero-in-degree group: alphabetical by id
            node = queue.popleft()
            result.append(mode_engines[node])
            for dependant in sorted(forward[node]):
                in_deg[dependant] -= 1
                if in_deg[dependant] == 0:
                    queue.append(dependant)

        if len(result) < len(mode_engines):
            cycle_members = [e for e, d in in_deg.items() if d > 0]
            raise RegistryError(
                f"Dependency cycle in mode '{mode.value}' among: {cycle_members}"
            )

        return result

    def parallel_groups_for_mode(
        self, mode: GDEMode
    ) -> list[list[EngineDescriptor]]:
        """Return execution phases for a mode as parallel groups.

        Each outer list is one sequential phase. Engines within an inner list
        have no mutual dependencies and may run concurrently.

        Example: if A and B have no relation, and C requires both A and B:
            [[A, B], [C]]
        """
        mode_engines = {d.id: d for d in self.for_mode(mode)}
        if not mode_engines:
            return []

        # Compute level (longest path from any root) for each engine
        level: dict[str, int] = {eid: 0 for eid in mode_engines}

        # Topological order first
        ordered = self.ordered_for_mode(mode)

        for desc in ordered:
            for dep_id in desc.requires:
                if dep_id in mode_engines:
                    level[desc.id] = max(level[desc.id], level[dep_id] + 1)

        # Group by level, stable-sorted within each level by id
        max_level = max(level.values()) if level else 0
        groups: list[list[EngineDescriptor]] = []
        for lvl in range(max_level + 1):
            group = sorted(
                [mode_engines[eid] for eid, depth in level.items() if depth == lvl],
                key=lambda d: d.id,
            )
            if group:
                groups.append(group)

        return groups


# ---------------------------------------------------------------------------
# Module-level default registry
# ---------------------------------------------------------------------------

#: The global registry instance used by the GDE at runtime.
#: Tests should create their own EngineRegistry() instances to stay isolated.
_default_registry: EngineRegistry = EngineRegistry()
_registration_loaded: bool = False


def get_default_registry() -> EngineRegistry:
    """Return the module-level default EngineRegistry, auto-loading descriptors on first call."""
    global _registration_loaded
    if not _registration_loaded:
        _registration_loaded = True
        import genesis_architect_pro.gde_engine_registration  # noqa: F401
    return _default_registry


def register(descriptor: EngineDescriptor) -> None:
    """Register a descriptor in the default registry."""
    _default_registry.register(descriptor)
