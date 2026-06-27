#!/usr/bin/env python3
"""
architecture_scorer.py - Genesis Architect PRO (advanced extension)

The base 0-100 scorer lives in the FREE core
(genesis_architect.core.architecture_scorer). Pro EXTENDS it - it does not
duplicate it - by adding:
  - the adaptive weight profiles (frontend-spa, backend-monolith, microservices,
    data-pipeline, library) on top of the free `default`
  - profile auto-detection from .genesis/evidence.json
  - score-history persistence + trend tracking

Public API is preserved: `score_project`, `score_label`, `PROFILES`,
`append_score_history`, `load_score_history`, `print_score_report`, plus the
dimension scorers re-exported from free core for the Pro test-suite.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

# Re-export the free base implementation (dimension scorers, helpers, label, etc).
from genesis_architect.core import architecture_scorer as _base
from genesis_architect.core.architecture_scorer import (  # noqa: F401
    score_label,
    print_score_report,
    _score_modularity,
    _score_coupling,
    _score_cohesion,
    _score_layering,
    _cycle_penalty,
)

# ---------------------------------------------------------------------------
# PRO: adaptive profiles (extend the free default)
# ---------------------------------------------------------------------------

PROFILES: dict[str, dict] = {
    **_base.PROFILES,  # inherits "default" from free core
    "frontend-spa":      {"modularity": 0.35, "coupling": 0.15, "cohesion": 0.35, "layering": 0.15},
    "backend-monolith":  {"modularity": 0.35, "coupling": 0.30, "cohesion": 0.15, "layering": 0.20},
    "microservices":     {"modularity": 0.30, "coupling": 0.20, "cohesion": 0.25, "layering": 0.25},
    "data-pipeline":     {"modularity": 0.35, "coupling": 0.25, "cohesion": 0.15, "layering": 0.25},
    "library":           {"modularity": 0.40, "coupling": 0.20, "cohesion": 0.30, "layering": 0.10},
}


# ---------------------------------------------------------------------------
# PRO: profile auto-detection from evidence.json
# ---------------------------------------------------------------------------

def _detect_profile(project_path: Path) -> str:
    """Infer scoring profile from archetype in .genesis/evidence.json."""
    evidence_path = Path(project_path) / ".genesis" / "evidence.json"
    if not evidence_path.exists():
        return "default"
    try:
        ev = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "default"

    archetype = ev.get("archetype", "").lower()
    tier = ev.get("tier", "").lower()

    if archetype == "frontend":
        return "frontend-spa"
    if archetype in ("service", "api"):
        if "micro" in tier or "micro" in archetype:
            return "microservices"
        return "backend-monolith"
    if archetype == "library":
        return "library"
    if "pipeline" in archetype or "etl" in archetype:
        return "data-pipeline"
    return "default"


# ---------------------------------------------------------------------------
# PRO: score_project that auto-detects profile and uses the adaptive profiles
# ---------------------------------------------------------------------------

def _score_confidence(module_count: int, cycle_count: int,
                      history_entries: int) -> tuple[float, str]:
    """
    Compute a confidence score (0.0–1.0) and human-readable basis string
    for a score_project() result.

    More modules → stronger signal. Historical comparisons → higher confidence.
    Many cycles → graph is uncertain → slightly lower confidence.
    """
    base = 0.65
    if module_count >= 10:
        base += 0.05
    if module_count >= 20:
        base += 0.05
    if module_count >= 50:
        base += 0.05
    if history_entries >= 3:
        base += 0.10
    elif history_entries >= 1:
        base += 0.05
    if cycle_count > 5:
        base -= 0.05
    conf = round(min(1.0, max(0.1, base)), 2)
    parts = [f"{module_count} modules analysed"]
    if history_entries > 0:
        parts.append(f"{history_entries} historical run(s)")
    if cycle_count > 0:
        parts.append(f"{cycle_count} cycle(s) detected")
    basis = ", ".join(parts)
    return conf, basis


def score_project(project_path: str | Path, profile: str | None = None,
                  language: str | None = None, rebuild_graph: bool = False,
                  profiles: dict | None = None) -> dict:
    """Pro scoring: auto-detect the adaptive profile, then delegate to the free
    core scorer with the full Pro profile set injected."""
    root = Path(project_path).resolve()
    if profile is None:
        profile = _detect_profile(root)
    result = _base.score_project(
        root, profile=profile, language=language,
        rebuild_graph=rebuild_graph, profiles=profiles or PROFILES,
    )
    # Step 2: inject confidence annotation (additive, backward-compatible)
    history = load_score_history(root)
    score_conf, score_basis = _score_confidence(
        result.get("module_count", 0),
        result.get("cycle_count", 0),
        len(history),
    )
    result["confidence"] = score_conf
    result["confidence_basis"] = score_basis
    return result


# ---------------------------------------------------------------------------
# PRO: score-history persistence (trend tracking)
# ---------------------------------------------------------------------------

def append_score_history(project_path: str | Path, score_result: dict) -> None:
    """Append score result to .genesis/score_history.jsonl."""
    root = Path(project_path).resolve()
    genesis_dir = root / ".genesis"
    genesis_dir.mkdir(parents=True, exist_ok=True)
    history_path = genesis_dir / "score_history.jsonl"
    record = {
        "timestamp": score_result["timestamp"],
        "total": score_result["total"],
        "modularity": score_result["modularity"],
        "coupling": score_result["coupling"],
        "cohesion": score_result["cohesion"],
        "layering": score_result["layering"],
        "profile": score_result["profile"],
        "cycle_count": score_result["cycle_count"],
        "module_count": score_result["module_count"],
    }
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def load_score_history(project_path: str | Path) -> list[dict]:
    """Load all historical scores from .genesis/score_history.jsonl."""
    root = Path(project_path).resolve()
    history_path = root / ".genesis" / "score_history.jsonl"
    if not history_path.exists():
        return []
    records = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records
