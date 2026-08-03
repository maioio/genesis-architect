#!/usr/bin/env python3
"""
fragility_classifier.py - Genesis Architect PRO

Classifies each module as STABLE / FRAGILE / VOLATILE based on:
  - Anti-pattern presence (from antipattern_detector)
  - Git churn level (from git_analyzer)
  - Test coverage proxy (does a test file exist for this module?)
  - Import graph fan_in / fan_out

Classification:
  STABLE   - No anti-patterns, LOW or STALE churn, test exists
  FRAGILE  - 1-2 minor anti-patterns OR medium churn OR no test
  VOLATILE - CRITICAL/HIGH anti-pattern OR HIGH churn + no test OR circular dep

Usage:
  python scripts/fragility_classifier.py [project_path]
  python scripts/fragility_classifier.py [project_path] --json
"""

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# import_graph is a pure primitive - import directly from free core.
from genesis_architect.core.import_graph import load_or_build
# antipattern detect_all must be the Pro version (7 detectors incl. advanced),
# so this stays on the Pro module.
from genesis_architect.pro.antipattern_detector import detect_all, AntiPattern
from genesis_architect.pro.git_analyzer import per_module_churn

# ---------------------------------------------------------------------------
# Test file detection
# ---------------------------------------------------------------------------

TEST_DIR_PATTERNS = ["tests", "test", "__tests__", "spec"]
TEST_FILE_PREFIXES = ["test_", "spec_"]
TEST_FILE_SUFFIXES = [".test.py", ".test.ts", ".test.js", ".spec.ts", ".spec.js", "_test.go", "_test.rs"]


def _find_test_files(project_path: Path) -> set[str]:
    """Collect all test-like files relative to project root."""
    test_files: set[str] = set()
    for f in project_path.rglob("*"):
        if not f.is_file():
            continue
        rel = str(f.relative_to(project_path)).replace("\\", "/")
        parts = rel.split("/")
        # In a test directory
        if any(p in TEST_DIR_PATTERNS for p in parts[:-1]):
            test_files.add(rel)
            continue
        name = f.name
        # Has test prefix
        if any(name.startswith(pfx) for pfx in TEST_FILE_PREFIXES):
            test_files.add(rel)
            continue
        # Has test suffix
        if any(name.endswith(sfx) for sfx in TEST_FILE_SUFFIXES):
            test_files.add(rel)
    return test_files


def _has_test(module_path: str, test_files: set[str]) -> bool:
    """Check if there is a corresponding test file for this module."""
    stem = Path(module_path).stem  # e.g. "app" from "src/app.py"
    for tf in test_files:
        tf_stem = Path(tf).stem
        if stem in tf_stem or tf_stem in stem:
            return True
    return False


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------

@dataclass
class ModuleClassification:
    module: str
    status: str           # STABLE | FRAGILE | VOLATILE
    reasons: list[str] = field(default_factory=list)
    anti_patterns: list[str] = field(default_factory=list)  # type names
    churn_level: str = "UNKNOWN"
    has_test: bool = False
    fan_in: int = 0
    fan_out: int = 0
    lines: int = 0
    layer: str = "unknown"
    go_hold_rewrite: str = "GO"  # GO | HOLD | REWRITE

    def to_dict(self) -> dict:
        return asdict(self)


def _classify_module(
    module: str,
    module_data: dict,
    module_antipatterns: list[AntiPattern],
    churn: dict | None,
    has_test: bool,
) -> ModuleClassification:
    reasons: list[str] = []
    ap_types = [p.type for p in module_antipatterns]
    ap_severities = [p.severity for p in module_antipatterns]

    churn_level = churn.get("churn_level", "UNKNOWN") if churn else "UNKNOWN"
    fan_in = module_data.get("fan_in", 0)
    fan_out = module_data.get("fan_out", 0)
    lines = module_data.get("lines", 0)

    # VOLATILE conditions (any one is sufficient)
    volatile = False
    if "CRITICAL" in ap_severities:
        volatile = True
        reasons.append(f"CRITICAL anti-pattern: {', '.join(t for t, s in zip(ap_types, ap_severities) if s == 'CRITICAL')}")
    if "circular-dep" in ap_types:
        volatile = True
        reasons.append("participates in circular dependency")
    if churn_level == "HIGH" and not has_test:
        volatile = True
        reasons.append("HIGH churn with no test coverage")
    if fan_in > 20:
        volatile = True
        reasons.append(f"extreme fan_in={fan_in} (affects all dependents on change)")
    if fan_out > 30:
        volatile = True
        reasons.append(f"extreme fan_out={fan_out} (god class)")

    if volatile:
        ghr = "REWRITE" if (fan_out > 30 or fan_in > 20 or "circular-dep" in ap_types) else "HOLD"
        return ModuleClassification(
            module=module, status="VOLATILE", reasons=reasons,
            anti_patterns=ap_types, churn_level=churn_level,
            has_test=has_test, fan_in=fan_in, fan_out=fan_out, lines=lines,
            layer=module_data.get("layer", "unknown"), go_hold_rewrite=ghr,
        )

    # FRAGILE conditions
    fragile = False
    if len(module_antipatterns) >= 1:
        fragile = True
        reasons.append(f"{len(module_antipatterns)} anti-pattern(s): {', '.join(set(ap_types))}")
    if churn_level == "MEDIUM":
        fragile = True
        reasons.append("MEDIUM churn")
    if not has_test and (fan_in > 3 or lines > 100):
        fragile = True
        reasons.append("no test coverage for a non-trivial module")
    if fan_in > 10:
        fragile = True
        reasons.append(f"fan_in={fan_in} (hub file)")

    if fragile:
        return ModuleClassification(
            module=module, status="FRAGILE", reasons=reasons,
            anti_patterns=ap_types, churn_level=churn_level,
            has_test=has_test, fan_in=fan_in, fan_out=fan_out, lines=lines,
            layer=module_data.get("layer", "unknown"), go_hold_rewrite="HOLD",
        )

    # STABLE
    return ModuleClassification(
        module=module, status="STABLE", reasons=[],
        anti_patterns=[], churn_level=churn_level,
        has_test=has_test, fan_in=fan_in, fan_out=fan_out, lines=lines,
        layer=module_data.get("layer", "unknown"), go_hold_rewrite="GO",
    )


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------

@dataclass
class FragilityReport:
    classifications: list[ModuleClassification] = field(default_factory=list)
    volatile_count: int = 0
    fragile_count: int = 0
    stable_count: int = 0
    total_modules: int = 0
    analysed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "classifications": [c.to_dict() for c in self.classifications],
            "volatile_count": self.volatile_count,
            "fragile_count": self.fragile_count,
            "stable_count": self.stable_count,
            "total_modules": self.total_modules,
            "analysed_at": self.analysed_at,
        }


def classify_all(project_path: str | Path, language: str | None = None,
                 git_days: int = 90, rebuild_graph: bool = False) -> FragilityReport:
    """Classify all modules in a project."""
    from datetime import UTC, datetime

    root = Path(project_path).resolve()

    graph = load_or_build(root, language=language, force_rebuild=rebuild_graph)
    modules = graph.get("modules", {})

    antipattern_report = detect_all(root, language=language, rebuild_graph=False)
    ap_by_module: dict[str, list[AntiPattern]] = {}
    for p in antipattern_report.patterns:
        ap_by_module.setdefault(p.file, []).append(p)

    churn_data = per_module_churn(root, days=git_days)
    test_files = _find_test_files(root)

    classifications: list[ModuleClassification] = []
    for mod, data in modules.items():
        c = _classify_module(
            module=mod,
            module_data=data,
            module_antipatterns=ap_by_module.get(mod, []),
            churn=churn_data.get(mod),
            has_test=_has_test(mod, test_files),
        )
        classifications.append(c)

    # Sort: VOLATILE first, then FRAGILE, then STABLE
    order = {"VOLATILE": 0, "FRAGILE": 1, "STABLE": 2}
    classifications.sort(key=lambda c: order.get(c.status, 3))

    counts = {"VOLATILE": 0, "FRAGILE": 0, "STABLE": 0}
    for c in classifications:
        counts[c.status] = counts.get(c.status, 0) + 1

    return FragilityReport(
        classifications=classifications,
        volatile_count=counts["VOLATILE"],
        fragile_count=counts["FRAGILE"],
        stable_count=counts["STABLE"],
        total_modules=len(classifications),
        analysed_at=datetime.now(UTC).isoformat(),
    )


def classify_module(entity: str, project_path: str | Path) -> dict | None:
    """Look up one module's fragility classification by name.

    `entity` is matched case-insensitively against the tail of each module's
    path (so a bare name like "auth_module" or "auth_module.py" matches
    "src/auth_module.py"). Returns None if no module matches. Used by the
    voice Companion's context-prefetch, which only has a bare entity name
    extracted from speech, not a full project-relative path.
    """
    report = classify_all(project_path)
    needle = entity.lower()
    for c in report.classifications:
        tail = Path(c.module).name.lower()
        if needle == tail or needle == tail.rsplit(".", 1)[0] or needle in c.module.lower():
            return c.to_dict()
    return None


def write_fragility_map(report: FragilityReport, output_path: Path) -> None:
    """Write FRAGILITY_MAP.md from a FragilityReport."""
    lines = [
        "# Fragility Map",
        "<!-- Generated by Genesis Architect PRO fragility_classifier.py -->",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|--------|-------|",
        f"| VOLATILE | {report.volatile_count} |",
        f"| FRAGILE  | {report.fragile_count} |",
        f"| STABLE   | {report.stable_count} |",
        f"| Total    | {report.total_modules} |",
        "",
        "> **VOLATILE**: do not modify without tests + review | "
        "**FRAGILE**: add tests before modifying | "
        "**STABLE**: safe to change",
        "",
    ]

    for status in ("VOLATILE", "FRAGILE", "STABLE"):
        group = [c for c in report.classifications if c.status == status]
        if not group:
            continue
        emoji = {"VOLATILE": "🔴", "FRAGILE": "🟡", "STABLE": "🟢"}[status]
        lines += [f"## {emoji} {status} Modules ({len(group)})", ""]
        lines += ["| Module | Layer | fan_in | fan_out | Churn | Tests | Action | Issues |",
                  "|--------|-------|--------|---------|-------|-------|--------|--------|"]
        for c in group:
            test_str = "yes" if c.has_test else "**no**"
            issues = "; ".join(c.reasons[:2]) if c.reasons else "-"
            lines.append(
                f"| `{c.module}` | {c.layer} | {c.fan_in} | {c.fan_out} | "
                f"{c.churn_level} | {test_str} | {c.go_hold_rewrite} | {issues} |"
            )
        lines.append("")

    lines += [
        "---",
        "",
        "_Generated by Genesis Architect PRO. Run `genesis recover [path]` to refresh._",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")


def print_report(report: FragilityReport) -> None:
    print(f"\nFragility Classification  ({report.total_modules} modules)")
    print(f"  VOLATILE: {report.volatile_count}  FRAGILE: {report.fragile_count}  STABLE: {report.stable_count}")

    volatile = [c for c in report.classifications if c.status == "VOLATILE"]
    if volatile:
        print("\nVOLATILE modules (do not touch without tests + review):")
        for c in volatile[:8]:
            print(f"  [{c.go_hold_rewrite}] {c.module}")
            for r in c.reasons[:2]:
                print(f"       - {r}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect PRO - Fragility Classifier"
    )
    parser.add_argument("project_path", nargs="?", default=".")
    parser.add_argument("--language", default=None)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-map", default=None,
                        help="Write FRAGILITY_MAP.md to this path")
    args = parser.parse_args()

    report = classify_all(args.project_path, language=args.language, git_days=args.days)

    if args.write_map:
        write_fragility_map(report, Path(args.write_map))
        print(f"Fragility map written to {args.write_map}", file=sys.stderr)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
