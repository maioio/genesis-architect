"""
dependency_index.py - Genesis Architect PRO

Pre-computed O(1) dependency lookup structures over a Genesis import graph.

The import graph dict (from import_graph.json / build_graph()) has the shape:
  {
    "modules": {
      "src/a.py": {"imports": ["src/b.py"], "imported_by": ["src/main.py"], ...},
      ...
    }
  }

DependencyIndex pre-computes two reverse maps in a single O(E) pass so that
every subsequent per-step or per-rule lookup is O(1) instead of O(E).

Public API
----------
  build_dependency_index(modules: dict) -> DependencyIndex
  compute_affected_scope(operations, index) -> AffectedScope

Both are pure functions with no side-effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class DependencyIndex:
    """
    Pre-computed bidirectional edge maps for a module dependency graph.

    incoming[X] = set of modules that import X   (callers / dependents)
    outgoing[X] = set of modules X imports        (dependencies)

    Both maps are built in a single O(E) pass by build_dependency_index().
    All subsequent queries are O(1) dict lookups.
    """
    incoming: dict[str, set[str]] = field(default_factory=dict)
    outgoing: dict[str, set[str]] = field(default_factory=dict)

    # Total edge count captured during construction (useful for validation)
    edge_count: int = 0

    def importers_of(self, module: str) -> set[str]:
        """Return modules that directly import *module* (O(1))."""
        return self.incoming.get(module, set())

    def imports_of(self, module: str) -> set[str]:
        """Return modules that *module* directly imports (O(1))."""
        return self.outgoing.get(module, set())

    def __len__(self) -> int:
        """Number of nodes (modules) in the index."""
        return len(self.outgoing)


@dataclass
class AffectedScope:
    """
    The minimal set of files that need re-analysis after a refactoring step.

    changed_files:  modules directly created/modified/deleted/moved by the step.
    consumer_files: modules that import at least one changed_file (one hop).
                    These need re-analysis because their dependency set changed.

    Note: consumer_files does NOT include changed_files; they are disjoint.
    """
    changed_files: list[str] = field(default_factory=list)
    consumer_files: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.changed_files) + len(self.consumer_files)

    def all_files(self) -> list[str]:
        """Sorted union of changed + consumer files."""
        return sorted(set(self.changed_files) | set(self.consumer_files))


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_dependency_index(modules: dict) -> DependencyIndex:
    """
    Build incoming and outgoing edge maps in a single O(E) pass.

    modules: the "modules" dict from a Genesis import graph
             (keys are relative file paths, values have an "imports" list).

    The algorithm:
      For each module M with imports [D1, D2, ...]:
        outgoing[M] = {D1, D2, ...}
        incoming[Di].add(M)  for each Di

    All edges are processed exactly once → O(E) time, O(V+E) space.
    """
    incoming: dict[str, set[str]] = {}
    outgoing: dict[str, set[str]] = {}
    edge_count = 0

    for mod, data in modules.items():
        deps = data.get("imports", [])
        outgoing[mod] = set(deps)
        edge_count += len(deps)
        for dep in deps:
            if dep not in incoming:
                incoming[dep] = set()
            incoming[dep].add(mod)

    # Ensure every module has an entry in both maps (even isolated nodes)
    for mod in modules:
        if mod not in incoming:
            incoming[mod] = set()

    return DependencyIndex(
        incoming=incoming,
        outgoing=outgoing,
        edge_count=edge_count,
    )


# ---------------------------------------------------------------------------
# Affected-scope computation
# ---------------------------------------------------------------------------

def compute_affected_scope(
    operations: list[dict],
    index: DependencyIndex,
) -> AffectedScope:
    """
    Compute the minimal set of modules to re-analyse after a set of operations.

    operations: list of dicts, each with at least:
        {"type": "CREATE"|"MODIFY"|"DELETE"|"MOVE", "path": "src/a.py"}
        MOVE operations may also carry "new_path": "src/auth/a.py".

    Algorithm:
      1. changed  = all paths mentioned in operations (O(ops))
      2. consumers = all modules in index.incoming[f] for f in changed (O(changed × fan_in))
         minus any module already in changed (keep sets disjoint)

    Both steps are O(1) per edge lookup after the index is built.
    """
    changed: set[str] = set()

    for op in operations:
        path = op.get("path", "")
        if path:
            changed.add(path)
        new_path = op.get("new_path", "")
        if new_path:
            changed.add(new_path)

    consumers: set[str] = set()
    for f in changed:
        for importer in index.incoming.get(f, set()):
            if importer not in changed:
                consumers.add(importer)

    return AffectedScope(
        changed_files=sorted(changed),
        consumer_files=sorted(consumers),
    )
