#!/usr/bin/env python3
"""
antipattern_detector.py - Genesis Architect (free core)

Detects structural anti-patterns from the import graph. All detection is
deterministic (no LLM) - pure graph analysis.

Free core ships the 4 base detectors:
  1. God Class       - excessive fan_out (does too much)
  2. Hub File        - excessive fan_in (everything depends on it)
  3. Circular Dep    - import cycles
  4. Dead Code       - fan_in=0, not entry point (orphan modules)

Pro EXTENDS this with advanced detectors (feature-envy, leaky-abstraction,
shotgun-surgery) by passing them to detect_all via `extra_detectors`.

Usage:
  python -m genesis_architect.core.antipattern_detector [project_path]
  python -m genesis_architect.core.antipattern_detector [project_path] --json
"""

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

from genesis_architect.core.import_graph import load_or_build, LAYER_VIOLATIONS

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
    # Step 2: confidence annotations (additive, backward-compatible)
    confidence: float = 1.0   # 0.0–1.0 detection certainty
    basis: str = ""           # human-readable explanation of confidence


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
# Confidence computation
# ---------------------------------------------------------------------------

def _antipattern_confidence(detector_type: str, metrics: dict) -> tuple[float, str]:
    """
    Return (confidence, basis) for a detected anti-pattern.

    confidence: 0.0–1.0. 1.0 = mathematically certain from graph data alone.
    basis: short sentence explaining what the score is based on.
    """
    if detector_type == "god-class":
        fan_out = metrics.get("fan_out", 0)
        threshold = metrics.get("threshold", GOD_CLASS_FAN_OUT)
        excess = fan_out - threshold
        # More excess above threshold = higher confidence
        conf = min(1.0, 0.6 + (excess / max(threshold, 1)) * 0.4)
        return round(conf, 2), f"fan_out={fan_out}, threshold={threshold}, excess={excess}"

    if detector_type == "hub-file":
        fan_in = metrics.get("fan_in", 0)
        threshold = metrics.get("threshold", HUB_FILE_FAN_IN)
        excess = fan_in - threshold
        conf = min(1.0, 0.6 + (excess / max(threshold, 1)) * 0.4)
        return round(conf, 2), f"fan_in={fan_in}, threshold={threshold}, excess={excess}"

    if detector_type == "circular-dep":
        length = metrics.get("cycle_length", 2)
        # Direct A→B→A cycle is unambiguous; longer cycles slightly less so
        conf = 1.0 if length == 2 else 0.92
        return conf, f"cycle_length={length}, deterministic graph cycle"

    if detector_type == "dead-code":
        lines = metrics.get("lines", 0)
        # Zero fan_in is factual; uncertainty comes from dynamic imports
        conf = 0.65 if lines > 100 else 0.80
        basis = f"fan_in=0, lines={lines}"
        if lines > 100:
            basis += "; larger files more likely dynamically imported"
        return conf, basis

    if detector_type == "feature-envy":
        ratio = metrics.get("ratio", 0.0)
        total = metrics.get("total_imports", 0)
        conf = min(1.0, 0.55 + ratio * 0.4 + min(total, 10) / 10 * 0.05)
        return round(conf, 2), f"import_ratio={ratio:.2f}, total_imports={total}"

    if detector_type == "leaky-abstraction":
        src = metrics.get("src_layer", "?")
        dst = metrics.get("dst_layer", "?")
        # Layer violations are definitional once layers are known
        return 0.90, f"layer_violation={src}→{dst}, based on directory heuristic"

    if detector_type == "shotgun-surgery":
        fan_in = metrics.get("fan_in", 0)
        lines = metrics.get("lines", 0)
        conf = min(1.0, 0.65 + min(fan_in - SHOTGUN_FAN_IN, 10) / 10 * 0.20)
        return round(conf, 2), f"fan_in={fan_in}, lines={lines}"

    return 0.75, "static graph analysis"


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def _detect_god_classes(modules: dict) -> list[AntiPattern]:
    patterns = []
    for mod, data in modules.items():
        fo = data.get("fan_out", 0)
        if fo > GOD_CLASS_FAN_OUT:
            severity = "CRITICAL" if fo > 30 else "HIGH"
            metrics = {"fan_out": fo, "threshold": GOD_CLASS_FAN_OUT, "lines": data.get("lines", 0)}
            conf, basis = _antipattern_confidence("god-class", metrics)
            patterns.append(AntiPattern(
                id=f"god-class-{mod.replace('/', '-').replace('.', '-')}",
                type="god-class",
                severity=severity,
                file=mod,
                description=(
                    f"'{mod}' imports {fo} modules — exceeds threshold of {GOD_CLASS_FAN_OUT}. "
                    f"This module does too much and should be split."
                ),
                metrics=metrics,
                affected_modules=data.get("imports", [])[:10],
                suggested_fix=(
                    f"Split '{mod}' into smaller modules grouped by responsibility. "
                    f"Each new module should import at most {GOD_CLASS_FAN_OUT // 2} others."
                ),
                confidence=conf,
                basis=basis,
            ))
    return patterns


def _detect_hub_files(modules: dict) -> list[AntiPattern]:
    patterns = []
    for mod, data in modules.items():
        fi = data.get("fan_in", 0)
        if fi > HUB_FILE_FAN_IN:
            severity = "CRITICAL" if fi > 20 else "HIGH"
            metrics = {"fan_in": fi, "threshold": HUB_FILE_FAN_IN}
            conf, basis = _antipattern_confidence("hub-file", metrics)
            patterns.append(AntiPattern(
                id=f"hub-file-{mod.replace('/', '-').replace('.', '-')}",
                type="hub-file",
                severity=severity,
                file=mod,
                description=(
                    f"'{mod}' is imported by {fi} modules — exceeds threshold of {HUB_FILE_FAN_IN}. "
                    f"Changes to this file cascade to {fi} dependents."
                ),
                metrics=metrics,
                affected_modules=data.get("imported_by", [])[:10],
                suggested_fix=(
                    f"Extract stable interfaces from '{mod}' into a separate module. "
                    f"Dependents import the interface, not the implementation."
                ),
                confidence=conf,
                basis=basis,
            ))
    return patterns


def _detect_circular_deps(cycles: list[list[str]]) -> list[AntiPattern]:
    patterns = []
    for i, cycle in enumerate(cycles):
        nodes = cycle[:-1]  # exclude repeated node at end
        severity = "CRITICAL" if len(nodes) == 2 else "HIGH"
        cycle_str = " -> ".join(cycle)
        metrics = {"cycle_length": len(nodes), "cycle": cycle}
        conf, basis = _antipattern_confidence("circular-dep", metrics)
        patterns.append(AntiPattern(
            id=f"circular-dep-{i}",
            type="circular-dep",
            severity=severity,
            file=nodes[0] if nodes else "",
            description=(
                f"Import cycle detected: {cycle_str}. "
                f"Circular dependencies prevent clean modularisation and testing."
            ),
            metrics=metrics,
            affected_modules=nodes,
            suggested_fix=(
                f"Break the cycle by extracting shared types/interfaces into a new module "
                f"that none of the cycle participants import from each other. "
                f"Cycle: {cycle_str}"
            ),
            confidence=conf,
            basis=basis,
        ))
    return patterns


def _detect_dead_code(modules: dict) -> list[AntiPattern]:
    patterns = []
    for mod, data in modules.items():
        if data.get("fan_in", 0) == 0 and not data.get("is_entry_point", False):
            lines = data.get("lines", 0)
            severity = "MEDIUM" if lines > 50 else "LOW"
            metrics = {"fan_in": 0, "lines": lines}
            conf, basis = _antipattern_confidence("dead-code", metrics)
            patterns.append(AntiPattern(
                id=f"dead-code-{mod.replace('/', '-').replace('.', '-')}",
                type="dead-code",
                severity=severity,
                file=mod,
                description=(
                    f"'{mod}' has no importers (fan_in=0) and is not an entry point. "
                    f"It may be dead code ({lines} lines)."
                ),
                metrics=metrics,
                affected_modules=[],
                suggested_fix=(
                    f"Verify '{mod}' is not used via dynamic import or as a script. "
                    f"If unused, delete it. If needed, document why it's standalone."
                ),
                confidence=conf,
                basis=basis,
            ))
    return patterns


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------

def detect_all(project_path: str | Path, language: str | None = None,
               rebuild_graph: bool = False,
               extra_detectors: list | None = None) -> AntiPatternReport:
    """Run the base anti-pattern detectors on a project.

    Free core runs the 4 base detectors. Pro passes its advanced detectors via
    `extra_detectors` - a list of callables, each `(modules, cycles) -> list`.
    """
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
    for detector in (extra_detectors or []):
        all_patterns.extend(detector(modules, cycles))

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
