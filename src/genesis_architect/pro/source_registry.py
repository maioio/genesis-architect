"""
Research Source Registry for Genesis Architect (Pro).

Genesis does not hard-code its research sources. They live in a registry that the
Research Intelligence and Developer Field Intelligence engines read at runtime:

  - a packaged default catalog (`data/research_sources.json`), and
  - optional per-project overrides at `.genesis/knowledge/research_sources.json`.

New sources can be added — or weights/routes retuned — **without changing the
engine**. This module loads, merges, ranks, and filters that catalog.

Reliability model:
  - Each source has a `tier` (official, source, security, qa, packages, field,
    blog, research, learning, market, local) with a tier `priority`, and an
    `evidence_weight` (0–1) used when ranking an Evidence Pack.
  - The `market` tier (e.g. Instagram) is a *demand/trend signal only* — never
    presented as engineering truth. This is enforced in `engineering_truth_*`
    helpers, which exclude it.

JSON is used (not YAML) to stay dependency-light — the project ships no PyYAML.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Tiers that are never treated as engineering truth (signal only).
_NON_TRUTH_TIERS = {"market"}

_PACKAGE_DATA = Path(__file__).with_name("data") / "research_sources.json"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

@dataclass
class Source:
    id: str
    name: str
    tier: str
    access: str = ""
    route: str = ""
    free: bool = False
    evidence_weight: float = 0.5
    url: str = ""
    note: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Source":
        return cls(
            id=str(d.get("id", "")),
            name=str(d.get("name", d.get("id", ""))),
            tier=str(d.get("tier", "")),
            access=str(d.get("access", "")),
            route=str(d.get("route", "")),
            free=bool(d.get("free", False)),
            evidence_weight=float(d.get("evidence_weight", 0.5)),
            url=str(d.get("url", "")),
            note=str(d.get("note", "")),
        )


@dataclass
class SourceRegistry:
    version: int = 0
    tiers: dict = field(default_factory=dict)            # tier -> {priority, role}
    sources: list = field(default_factory=list)          # list[Source]
    engine_profiles: dict = field(default_factory=dict)  # engine -> [tiers]

    # -- lookups ------------------------------------------------------------

    def tier_priority(self, tier: str) -> int:
        return int(self.tiers.get(tier, {}).get("priority", 0))

    def get(self, source_id: str) -> Source | None:
        for s in self.sources:
            if s.id == source_id:
                return s
        return None

    def by_tier(self, tier: str) -> list:
        return [s for s in self.sources if s.tier == tier]

    def rank_score(self, source: Source) -> float:
        """Combined ranking: tier priority scaled by the source's evidence
        weight. Higher = consult earlier / trust more."""
        return self.tier_priority(source.tier) * source.evidence_weight

    def ranked(self, *, free_only: bool = False,
               include_market: bool = True) -> list:
        """All sources, most authoritative first. `free_only` keeps only
        free-tier sources; `include_market` can drop signal-only tiers."""
        pool = [s for s in self.sources
                if (not free_only or s.free)
                and (include_market or s.tier not in _NON_TRUTH_TIERS)]
        return sorted(pool, key=self.rank_score, reverse=True)

    def for_engine(self, engine: str, *, free_only: bool = False) -> list:
        """Ranked sources for an engine, restricted to its declared tiers
        (engine_profiles). Unknown engine -> all sources."""
        tiers = self.engine_profiles.get(engine)
        pool = self.ranked(free_only=free_only)
        if tiers is None:
            return pool
        allowed = set(tiers)
        return [s for s in pool if s.tier in allowed]

    def engineering_truth_sources(self, *, free_only: bool = False) -> list:
        """Ranked sources EXCLUDING signal-only tiers (market). Use this when a
        claim must be backed by engineering truth, not demand signal."""
        return self.ranked(free_only=free_only, include_market=False)

    def is_engineering_truth(self, source_id: str) -> bool:
        s = self.get(source_id)
        return bool(s and s.tier not in _NON_TRUTH_TIERS)


# ---------------------------------------------------------------------------
# Loading + merging (package default + project override)
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _project_override_path(project_root: Path) -> Path:
    return Path(project_root) / ".genesis" / "knowledge" / "research_sources.json"


def _build(data: dict) -> SourceRegistry:
    return SourceRegistry(
        version=int(data.get("version", 0)),
        tiers=dict(data.get("tiers", {})),
        sources=[Source.from_dict(s) for s in data.get("sources", [])],
        engine_profiles=dict(data.get("engine_profiles", {})),
    )


def load_registry(project_root: Path | str = ".") -> SourceRegistry:
    """Load the packaged default registry, then merge any per-project override.

    Override semantics (additive + override-by-id):
      - tiers / engine_profiles from the override update the defaults.
      - a source in the override with an existing id REPLACES that source;
        a new id is ADDED. Nothing is removed implicitly.
    This is how new sources are added without changing the engine.
    """
    base = _load_json(_PACKAGE_DATA)
    reg = _build(base)

    override = _load_json(_project_override_path(Path(project_root)))
    if not override:
        return reg

    if "tiers" in override:
        reg.tiers.update(override["tiers"])
    if "engine_profiles" in override:
        reg.engine_profiles.update(override["engine_profiles"])
    if "sources" in override:
        by_id = {s.id: s for s in reg.sources}
        for sd in override["sources"]:
            s = Source.from_dict(sd)
            by_id[s.id] = s  # replace or add
        reg.sources = list(by_id.values())
    return reg


def add_project_source(source: dict, project_root: Path | str = ".") -> bool:
    """Persist a new/overriding source into the per-project override file, so it
    is picked up on the next load. Returns True on success. Never raises."""
    if not source.get("id") or not source.get("tier"):
        return False
    path = _project_override_path(Path(project_root))
    current = _load_json(path)
    sources = current.get("sources", [])
    sources = [s for s in sources if s.get("id") != source["id"]]
    sources.append(source)
    current["sources"] = sources
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False
