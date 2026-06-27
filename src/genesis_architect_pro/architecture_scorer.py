#!/usr/bin/env python3
"""
architecture_scorer.py - Genesis Architect PRO

Computes a 0-100 architecture quality score across 4 dimensions:
  - modularity  (40%): single responsibility, low fan-out
  - coupling    (25%): low fan-in, no hub files
  - cohesion    (20%): internal vs external imports per module
  - layering    (15%): cross-layer import violations

Adaptive profiles adjust dimension weights for project type:
  default, frontend-spa, backend-monolith, microservices, data-pipeline, library

Score is appended to .genesis/score_history.jsonl on each run.

Usage:
  python scripts/architecture_scorer.py [project_path]
  python scripts/architecture_scorer.py [project_path] --profile microservices
  python scripts/architecture_scorer.py [project_path] --json
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from genesis_architect_pro.import_graph import load_or_build

# ---------------------------------------------------------------------------
# Adaptive scoring profiles
# (modularity, coupling, cohesion, layering) weights, sum to 1.0
# ---------------------------------------------------------------------------

PROFILES: dict[str, dict] = {
    "default":           {"modularity": 0.40, "coupling": 0.25, "cohesion": 0.20, "layering": 0.15},
    "frontend-spa":      {"modularity": 0.35, "coupling": 0.15, "cohesion": 0.35, "layering": 0.15},
    "backend-monolith":  {"modularity": 0.35, "coupling": 0.30, "cohesion": 0.15, "layering": 0.20},
    "microservices":     {"modularity": 0.30, "coupling": 0.20, "cohesion": 0.25, "layering": 0.25},
    "data-pipeline":     {"modularity": 0.35, "coupling": 0.25, "cohesion": 0.15, "layering": 0.25},
    "library":           {"modularity": 0.40, "coupling": 0.20, "cohesion": 0.30, "layering": 0.10},
}

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Hub file: fan_in above this = high coupling smell
HUB_FAN_IN_THRESHOLD = 10
# God class: fan_out above this = low modularity smell
GOD_FAN_OUT_THRESHOLD = 15
# Cohesion: ratio of internal imports below this = low cohesion
LOW_COHESION_THRESHOLD = 0.3

# Layer violation pairs: (importer_layer, imported_layer) that should not occur
LAYER_VIOLATIONS: set[tuple[str, str]] = {
    ("domain", "infrastructure"),
    ("domain", "application"),
    ("domain", "presentation"),
    ("application", "infrastructure"),
    ("application", "presentation"),
    ("shared", "domain"),
    ("shared", "application"),
    ("shared", "infrastructure"),
    ("shared", "presentation"),
}


# ---------------------------------------------------------------------------
# Profile auto-detection from evidence.json
# ---------------------------------------------------------------------------

def _detect_profile(project_path: Path) -> str:
    """Infer scoring profile from archetype in .genesis/evidence.json."""
    evidence_path = project_path / ".genesis" / "evidence.json"
    if not evidence_path.exists():
        return "default"
    try:
        ev = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "default"

    archetype = ev.get("archetype", "").lower()
    tier = ev.get("tier", "").lower()
    lang = ev.get("language", "").lower()

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
# Dimension scorers
# ---------------------------------------------------------------------------

def _score_modularity(modules: dict) -> tuple[float, list[str]]:
    """
    Modularity: fraction of modules with fan_out <= GOD_FAN_OUT_THRESHOLD.
    God classes (fan_out > threshold) heavily penalise this score.
    Returns (score_0_to_100, [issues])
    """
    if not modules:
        return 100.0, []

    issues: list[str] = []
    total = len(modules)
    violations = 0

    for mod, data in modules.items():
        fo = data.get("fan_out", 0)
        if fo > GOD_FAN_OUT_THRESHOLD:
            violations += 1
            issues.append(f"God class: {mod} (fan_out={fo})")

    # Base score from violation fraction
    violation_ratio = violations / total
    score = max(0.0, 100.0 - (violation_ratio * 100.0 * 2.0))  # 2x penalty
    return round(score, 1), issues


def _score_coupling(modules: dict) -> tuple[float, list[str]]:
    """
    Coupling: fraction of modules with fan_in <= HUB_FAN_IN_THRESHOLD.
    Hub files (high fan_in) are coupling smells. Low average fan_in is good.
    """
    if not modules:
        return 100.0, []

    issues: list[str] = []
    fan_ins = [data.get("fan_in", 0) for data in modules.values()]
    total = len(modules)
    hub_count = 0

    for mod, data in modules.items():
        fi = data.get("fan_in", 0)
        if fi > HUB_FAN_IN_THRESHOLD:
            hub_count += 1
            issues.append(f"Hub file: {mod} (fan_in={fi})")

    hub_ratio = hub_count / total
    avg_fan_in = sum(fan_ins) / total if fan_ins else 0

    # Penalise hub ratio heavily + penalise high average fan_in
    hub_penalty = hub_ratio * 60.0
    avg_penalty = min(40.0, (avg_fan_in / 5.0) * 10.0)  # cap at 40 pts
    score = max(0.0, 100.0 - hub_penalty - avg_penalty)
    return round(score, 1), issues


def _score_cohesion(modules: dict) -> tuple[float, list[str]]:
    """
    Cohesion: for each module, ratio of imports that stay within the same layer.
    High inter-layer imports = low cohesion.
    """
    if not modules:
        return 100.0, []

    issues: list[str] = []
    scores: list[float] = []

    # Build layer map
    layer_map = {mod: data.get("layer", "unknown") for mod, data in modules.items()}

    for mod, data in modules.items():
        my_layer = data.get("layer", "unknown")
        imports = data.get("imports", [])
        if not imports:
            scores.append(100.0)
            continue

        internal = sum(1 for imp in imports if layer_map.get(imp) == my_layer)
        ratio = internal / len(imports)
        mod_score = ratio * 100.0
        scores.append(mod_score)

        if ratio < LOW_COHESION_THRESHOLD and len(imports) >= 3:
            issues.append(
                f"Low cohesion: {mod} ({int(ratio*100)}% internal imports, "
                f"layer={my_layer})"
            )

    avg = sum(scores) / len(scores) if scores else 100.0
    return round(avg, 1), issues


def _score_layering(modules: dict) -> tuple[float, list[str]]:
    """
    Layering: penalise cross-layer import violations.
    Each violation reduces score proportionally to module count.
    """
    if not modules:
        return 100.0, []

    issues: list[str] = []
    layer_map = {mod: data.get("layer", "unknown") for mod, data in modules.items()}
    total_imports = sum(len(data.get("imports", [])) for data in modules.values())

    if total_imports == 0:
        return 100.0, []

    violation_count = 0
    for mod, data in modules.items():
        src_layer = layer_map.get(mod, "unknown")
        for imp in data.get("imports", []):
            dst_layer = layer_map.get(imp, "unknown")
            if src_layer != "unknown" and dst_layer != "unknown":
                if (src_layer, dst_layer) in LAYER_VIOLATIONS:
                    violation_count += 1
                    issues.append(
                        f"Layer violation: {mod} ({src_layer}) -> {imp} ({dst_layer})"
                    )

    violation_ratio = violation_count / total_imports
    score = max(0.0, 100.0 - (violation_ratio * 200.0))  # strict: 2x penalty
    return round(score, 1), issues[:20]  # cap output


# ---------------------------------------------------------------------------
# Cycle penalty (cross-cutting)
# ---------------------------------------------------------------------------

def _cycle_penalty(cycle_count: int) -> float:
    """Each cycle shaves points from the total score."""
    return min(30.0, cycle_count * 5.0)


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

def score_project(project_path: str | Path, profile: str | None = None,
                  language: str | None = None, rebuild_graph: bool = False) -> dict:
    """
    Compute architecture score for a project.

    Returns:
        {
          "total": int,           # 0-100 composite
          "modularity": float,
          "coupling": float,
          "cohesion": float,
          "layering": float,
          "profile": str,
          "cycle_penalty": float,
          "issues": {
            "modularity": [...],
            "coupling": [...],
            "cohesion": [...],
            "layering": [...],
          },
          "module_count": int,
          "cycle_count": int,
          "dark_module_count": int,
          "timestamp": str,
        }
    """
    root = Path(project_path).resolve()

    # Load or build graph
    graph = load_or_build(root, language=language, force_rebuild=rebuild_graph)
    modules = graph.get("modules", {})
    cycles = graph.get("cycles", [])
    dark_modules = graph.get("dark_modules", [])

    # Detect profile
    if profile is None:
        profile = _detect_profile(root)
    if profile not in PROFILES:
        profile = "default"
    weights = PROFILES[profile]

    # Score each dimension
    mod_score, mod_issues = _score_modularity(modules)
    cpl_score, cpl_issues = _score_coupling(modules)
    coh_score, coh_issues = _score_cohesion(modules)
    lay_score, lay_issues = _score_layering(modules)

    # Weighted composite (before cycle penalty)
    weighted = (
        mod_score * weights["modularity"] +
        cpl_score * weights["coupling"] +
        coh_score * weights["cohesion"] +
        lay_score * weights["layering"]
    )

    # Cycle penalty
    penalty = _cycle_penalty(len(cycles))
    total = max(0, round(weighted - penalty))

    result = {
        "total": total,
        "modularity": mod_score,
        "coupling": cpl_score,
        "cohesion": coh_score,
        "layering": lay_score,
        "profile": profile,
        "weights": weights,
        "cycle_penalty": penalty,
        "issues": {
            "modularity": mod_issues,
            "coupling": cpl_issues,
            "cohesion": coh_issues,
            "layering": lay_issues[:20],
        },
        "module_count": graph.get("module_count", len(modules)),
        "cycle_count": len(cycles),
        "dark_module_count": len(dark_modules),
        "language": graph.get("language", "unknown"),
        "timestamp": datetime.now(UTC).isoformat(),
    }

    return result


# ---------------------------------------------------------------------------
# Score history persistence
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


# ---------------------------------------------------------------------------
# Score label
# ---------------------------------------------------------------------------

def score_label(total: int) -> str:
    if total >= 80:
        return "EXCELLENT"
    if total >= 65:
        return "GOOD"
    if total >= 50:
        return "FAIR"
    if total >= 35:
        return "POOR"
    return "CRITICAL"


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_score_report(result: dict, project_path: str = ".") -> None:
    total = result["total"]
    label = score_label(total)
    print(f"\nArchitecture Score: {total}/100  [{label}]")
    print(f"Profile: {result['profile']}  |  Language: {result['language']}")
    print(f"Modules: {result['module_count']}  |  Cycles: {result['cycle_count']}  |  "
          f"Dark: {result['dark_module_count']}")
    print()
    print(f"  Modularity  {result['modularity']:>5.1f}/100  (weight {result['weights']['modularity']:.0%})")
    print(f"  Coupling    {result['coupling']:>5.1f}/100  (weight {result['weights']['coupling']:.0%})")
    print(f"  Cohesion    {result['cohesion']:>5.1f}/100  (weight {result['weights']['cohesion']:.0%})")
    print(f"  Layering    {result['layering']:>5.1f}/100  (weight {result['weights']['layering']:.0%})")
    if result["cycle_penalty"] > 0:
        print(f"  Cycles      -{result['cycle_penalty']:.1f} pts  ({result['cycle_count']} cycle(s) detected)")

    all_issues: list[str] = []
    for dim_issues in result["issues"].values():
        all_issues.extend(dim_issues[:3])
    if all_issues:
        print(f"\nTop issues ({len(all_issues)} shown):")
        for issue in all_issues[:8]:
            print(f"  - {issue}")

    # Trend (if history exists)
    history = load_score_history(project_path)
    if len(history) >= 2:
        prev = history[-2]["total"]
        delta = total - prev
        arrow = "+" if delta >= 0 else ""
        print(f"\nTrend: {arrow}{delta} from previous scan ({prev} -> {total})")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect PRO - Architecture Scorer"
    )
    parser.add_argument("project_path", nargs="?", default=".")
    parser.add_argument("--profile", default=None,
                        choices=list(PROFILES.keys()),
                        help="Scoring profile (default: auto-detect from evidence.json)")
    parser.add_argument("--language", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--rebuild", action="store_true",
                        help="Force rebuild of import graph cache")
    parser.add_argument("--no-save", action="store_true",
                        help="Skip appending to score_history.jsonl")
    args = parser.parse_args()

    result = score_project(
        args.project_path,
        profile=args.profile,
        language=args.language,
        rebuild_graph=args.rebuild,
    )

    if not args.no_save:
        append_score_history(args.project_path, result)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_score_report(result, args.project_path)

    sys.exit(0 if result["total"] >= 50 else 1)


if __name__ == "__main__":
    main()
