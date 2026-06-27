#!/usr/bin/env python3
"""
antipattern_detector.py - Genesis Architect PRO

Detects 7 structural anti-patterns from the import graph.
All detection is deterministic (no LLM) - pure graph analysis.

Anti-patterns detected:
  1. God Class       - excessive fan_out (does too much)
  2. Hub File        - excessive fan_in (everything depends on it)
  3. Circular Dep    - import cycles
  4. Dead Code       - fan_in=0, not entry point (orphan modules)
  5. Feature Envy    - most imports from one external module (belongs there)
  6. Leaky Abstr.    - low-layer imports from high-layer (layer violation)
  7. Shotgun Surgery - single utility imported by >N modules (fragile coupling)

Usage:
  python scripts/antipattern_detector.py [project_path]
  python scripts/antipattern_detector.py [project_path] --json
"""

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

from genesis_architect_pro.import_graph import load_or_build, LAYER_VIOLATIONS

# ---------------------------------------------------------------------------
# Thresholds (tunable via .genesis.rules.yml in future)
# ---------------------------------------------------------------------------

GOD_CLASS_FAN_OUT = 15        # fan_out above this = god class
HUB_FILE_FAN_IN = 10          # fan_in above this = hub file
FEATURE_ENVY_RATIO = 0.65     # >65% imports from one module = feature envy
SHOTGUN_FAN_IN = 8            # utility imported by >8 modules = shotgun risk
MIN_IMPORTS_FOR_ENVY = 4      # minimum imports before feature envy check


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class AntiPattern:
    id: str
    type: str                 # god-class | hub-file | circular-dep | dead-code |
                              # feature-envy | leaky-abstraction | shotgun-surgery
    severity: str             # CRITICAL | HIGH | MEDIUM | LOW
    file: str
    description: str
    metrics: dict = field(default_factory=dict)
    affected_modules: list[str] = field(default_factory=list)
    suggested_fix: str = ""


@dataclass
class AntiPatternReport:
    patterns: list[AntiPattern] = field(default_factory=list)
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    module_count: int = 0
    analysed_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def _detect_god_classes(modules: dict) -> list[AntiPattern]:
    patterns = []
    for mod, data in modules.items():
        fo = data.get("fan_out", 0)
        if fo > GOD_CLASS_FAN_OUT:
            severity = "CRITICAL" if fo > 30 else "HIGH"
            patterns.append(AntiPattern(
                id=f"god-class-{mod.replace('/', '-').replace('.', '-')}",
                type="god-class",
                severity=severity,
                file=mod,
                description=(
                    f"'{mod}' imports {fo} modules — exceeds threshold of {GOD_CLASS_FAN_OUT}. "
                    f"This module does too much and should be split."
                ),
                metrics={"fan_out": fo, "threshold": GOD_CLASS_FAN_OUT, "lines": data.get("lines", 0)},
                affected_modules=data.get("imports", [])[:10],
                suggested_fix=(
                    f"Split '{mod}' into smaller modules grouped by responsibility. "
                    f"Each new module should import at most {GOD_CLASS_FAN_OUT // 2} others."
                ),
            ))
    return patterns


def _detect_hub_files(modules: dict) -> list[AntiPattern]:
    patterns = []
    for mod, data in modules.items():
        fi = data.get("fan_in", 0)
        if fi > HUB_FILE_FAN_IN:
            severity = "CRITICAL" if fi > 20 else "HIGH"
            patterns.append(AntiPattern(
                id=f"hub-file-{mod.replace('/', '-').replace('.', '-')}",
                type="hub-file",
                severity=severity,
                file=mod,
                description=(
                    f"'{mod}' is imported by {fi} modules — exceeds threshold of {HUB_FILE_FAN_IN}. "
                    f"Changes to this file cascade to {fi} dependents."
                ),
                metrics={"fan_in": fi, "threshold": HUB_FILE_FAN_IN},
                affected_modules=data.get("imported_by", [])[:10],
                suggested_fix=(
                    f"Extract stable interfaces from '{mod}' into a separate module. "
                    f"Dependents import the interface, not the implementation."
                ),
            ))
    return patterns


def _detect_circular_deps(cycles: list[list[str]]) -> list[AntiPattern]:
    patterns = []
    for i, cycle in enumerate(cycles):
        nodes = cycle[:-1]  # exclude repeated node at end
        severity = "CRITICAL" if len(nodes) == 2 else "HIGH"
        cycle_str = " -> ".join(cycle)
        patterns.append(AntiPattern(
            id=f"circular-dep-{i}",
            type="circular-dep",
            severity=severity,
            file=nodes[0] if nodes else "",
            description=(
                f"Import cycle detected: {cycle_str}. "
                f"Circular dependencies prevent clean modularisation and testing."
            ),
            metrics={"cycle_length": len(nodes), "cycle": cycle},
            affected_modules=nodes,
            suggested_fix=(
                f"Break the cycle by extracting shared types/interfaces into a new module "
                f"that none of the cycle participants import from each other. "
                f"Cycle: {cycle_str}"
            ),
        ))
    return patterns


def _detect_dead_code(modules: dict) -> list[AntiPattern]:
    patterns = []
    for mod, data in modules.items():
        if data.get("fan_in", 0) == 0 and not data.get("is_entry_point", False):
            lines = data.get("lines", 0)
            severity = "MEDIUM" if lines > 50 else "LOW"
            patterns.append(AntiPattern(
                id=f"dead-code-{mod.replace('/', '-').replace('.', '-')}",
                type="dead-code",
                severity=severity,
                file=mod,
                description=(
                    f"'{mod}' has no importers (fan_in=0) and is not an entry point. "
                    f"It may be dead code ({lines} lines)."
                ),
                metrics={"fan_in": 0, "lines": lines},
                affected_modules=[],
                suggested_fix=(
                    f"Verify '{mod}' is not used via dynamic import or as a script. "
                    f"If unused, delete it. If needed, document why it's standalone."
                ),
            ))
    return patterns


def _detect_feature_envy(modules: dict) -> list[AntiPattern]:
    """Module that imports mostly from one other module - it may belong there."""
    patterns = []
    for mod, data in modules.items():
        imports = data.get("imports", [])
        if len(imports) < MIN_IMPORTS_FOR_ENVY:
            continue

        # Count imports per external module
        from collections import Counter
        counts = Counter(imports)
        top_target, top_count = counts.most_common(1)[0]
        ratio = top_count / len(imports)

        if ratio > FEATURE_ENVY_RATIO:
            patterns.append(AntiPattern(
                id=f"feature-envy-{mod.replace('/', '-').replace('.', '-')}",
                type="feature-envy",
                severity="MEDIUM",
                file=mod,
                description=(
                    f"'{mod}' imports {int(ratio*100)}% of its dependencies from '{top_target}'. "
                    f"This module may have feature envy and belong closer to '{top_target}'."
                ),
                metrics={
                    "top_target": top_target,
                    "top_count": top_count,
                    "total_imports": len(imports),
                    "ratio": round(ratio, 2),
                },
                affected_modules=[top_target],
                suggested_fix=(
                    f"Consider moving '{mod}' into the same package as '{top_target}', "
                    f"or extracting shared behaviour into a dedicated module."
                ),
            ))
    return patterns


def _detect_leaky_abstractions(modules: dict) -> list[AntiPattern]:
    """Low-layer modules importing from high-layer = architectural inversion."""
    patterns = []
    layer_map = {mod: data.get("layer", "unknown") for mod, data in modules.items()}

    for mod, data in modules.items():
        src_layer = layer_map.get(mod, "unknown")
        for imp in data.get("imports", []):
            dst_layer = layer_map.get(imp, "unknown")
            if src_layer != "unknown" and dst_layer != "unknown":
                if (src_layer, dst_layer) in LAYER_VIOLATIONS:
                    ap_id = f"leaky-{mod.replace('/', '-').replace('.', '-')}-to-{imp.replace('/', '-').replace('.', '-')}"
                    patterns.append(AntiPattern(
                        id=ap_id,
                        type="leaky-abstraction",
                        severity="HIGH",
                        file=mod,
                        description=(
                            f"Layer violation: '{mod}' ({src_layer}) imports from "
                            f"'{imp}' ({dst_layer}). "
                            f"{src_layer.capitalize()} should not depend on {dst_layer}."
                        ),
                        metrics={"src_layer": src_layer, "dst_layer": dst_layer},
                        affected_modules=[imp],
                        suggested_fix=(
                            f"Move '{imp}' to a layer that '{mod}' ({src_layer}) is allowed to depend on, "
                            f"or introduce an interface/abstraction that {src_layer} depends on instead."
                        ),
                    ))
    # Deduplicate by module pair (keep first occurrence per src)
    seen_src: set[str] = set()
    deduped = []
    for p in patterns:
        if p.file not in seen_src:
            deduped.append(p)
            seen_src.add(p.file)
    return deduped[:20]  # cap output


def _detect_shotgun_surgery(modules: dict) -> list[AntiPattern]:
    """
    Utility module imported by many other modules - a change cascades everywhere.
    Different from hub-file: this targets small utility modules, not large central ones.
    """
    patterns = []
    for mod, data in modules.items():
        fi = data.get("fan_in", 0)
        fo = data.get("fan_out", 0)
        lines = data.get("lines", 0)

        # Shotgun: high fan_in, low fan_out (utility, not hub), small file
        if fi > SHOTGUN_FAN_IN and fo <= 3 and lines < 200:
            patterns.append(AntiPattern(
                id=f"shotgun-{mod.replace('/', '-').replace('.', '-')}",
                type="shotgun-surgery",
                severity="MEDIUM",
                file=mod,
                description=(
                    f"'{mod}' is a small utility ({lines} lines, fan_out={fo}) "
                    f"imported by {fi} modules. Any change breaks {fi} dependents."
                ),
                metrics={"fan_in": fi, "fan_out": fo, "lines": lines},
                affected_modules=data.get("imported_by", [])[:10],
                suggested_fix=(
                    f"Stabilise the public API of '{mod}' or split it so dependents "
                    f"import only what they need. Consider a facade pattern."
                ),
            ))
    return patterns


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------

def detect_all(project_path: str | Path, language: str | None = None,
               rebuild_graph: bool = False) -> AntiPatternReport:
    """Run all anti-pattern detectors on a project."""
    from datetime import UTC, datetime

    root = Path(project_path).resolve()
    graph = load_or_build(root, language=language, force_rebuild=rebuild_graph)
    modules = graph.get("modules", {})
    cycles = graph.get("cycles", [])

    all_patterns: list[AntiPattern] = []
    all_patterns.extend(_detect_god_classes(modules))
    all_patterns.extend(_detect_hub_files(modules))
    all_patterns.extend(_detect_circular_deps(cycles))
    all_patterns.extend(_detect_dead_code(modules))
    all_patterns.extend(_detect_feature_envy(modules))
    all_patterns.extend(_detect_leaky_abstractions(modules))
    all_patterns.extend(_detect_shotgun_surgery(modules))

    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    all_patterns.sort(key=lambda p: severity_order.get(p.severity, 4))

    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for p in all_patterns:
        counts[p.severity] = counts.get(p.severity, 0) + 1

    return AntiPatternReport(
        patterns=all_patterns,
        critical_count=counts["CRITICAL"],
        high_count=counts["HIGH"],
        medium_count=counts["MEDIUM"],
        low_count=counts["LOW"],
        module_count=len(modules),
        analysed_at=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(report: AntiPatternReport) -> None:
    total = len(report.patterns)
    print(f"\nAnti-Pattern Report  ({report.module_count} modules analysed)")
    print(f"  CRITICAL: {report.critical_count}  HIGH: {report.high_count}  "
          f"MEDIUM: {report.medium_count}  LOW: {report.low_count}  "
          f"Total: {total}")

    if not report.patterns:
        print("\n  No anti-patterns detected.")
        return

    icons = {"CRITICAL": "[!!]", "HIGH": "[! ]", "MEDIUM": "[ *]", "LOW": "[  ]"}
    for p in report.patterns:
        icon = icons.get(p.severity, "[  ]")
        print(f"\n{icon} {p.type.upper()}  {p.file}")
        print(f"    {p.description}")
        if p.suggested_fix:
            print(f"    Fix: {p.suggested_fix}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect PRO - Anti-Pattern Detector"
    )
    parser.add_argument("project_path", nargs="?", default=".")
    parser.add_argument("--language", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    report = detect_all(args.project_path, language=args.language,
                        rebuild_graph=args.rebuild)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_report(report)

    sys.exit(1 if report.critical_count > 0 else 0)


if __name__ == "__main__":
    main()
