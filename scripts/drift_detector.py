#!/usr/bin/env python3
"""
drift_detector.py - Detect architecture drift from initial ADR decisions.

Compares current project structure against docs/adr/001-initial-architecture.md.
Run periodically to catch unplanned structural changes.

Usage:
  python scripts/drift_detector.py [project_path]
  genesis drift                     (from companion mode)
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass


ADR_PATH = "docs/adr/001-initial-architecture.md"
SRC_DIR = "src"
GROWTH_THRESHOLD = 10  # flag if any directory grows 10x from initial count


@dataclass
class DriftReport:
    new_dirs: list[str]
    missing_dirs: list[str]
    grown_dirs: list[tuple[str, int, int]]
    adr_found: bool


def _safe_path(base: Path, target: Path) -> Path:
    if not target.resolve().is_relative_to(base.resolve()):
        raise PermissionError(f"Path outside project: {target}")
    return target


def _parse_adr_structure(adr_content: str) -> list[str]:
    """Extract expected top-level directory names from ADR."""
    dirs = []
    in_structure = False
    for line in adr_content.splitlines():
        if "Expected Structure" in line or "Folder Structure" in line or "```" in line:
            in_structure = "```" in line and in_structure is False or in_structure
            if "```" in line and in_structure:
                in_structure = not in_structure
                continue
        if in_structure:
            match = re.match(r"^[├└│]\s+(\w[\w.-]*)/", line.strip())
            if match:
                dirs.append(match.group(1))
    # Also look for decisions table
    for line in adr_content.splitlines():
        match = re.search(r"\|\s*Directory[^|]*\|\s*`?([a-z][a-z0-9_-]+/?)` ", line)
        if match:
            dirs.append(match.group(1).rstrip("/"))
    return list(set(dirs)) if dirs else ["src", "tests", "docs"]


def _count_files(directory: Path) -> dict[str, int]:
    counts = {}
    if not directory.exists():
        return counts
    for item in directory.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            counts[item.name] = sum(1 for _ in item.rglob("*") if _.is_file())
    return counts


def detect_drift(project_path: str = ".") -> DriftReport:
    root = Path(project_path).resolve()
    adr_file = root / ADR_PATH

    adr_found = adr_file.exists()
    expected_dirs: list[str] = []

    if adr_found:
        try:
            _safe_path(root, adr_file)
            content = adr_file.read_text(encoding="utf-8")
            expected_dirs = _parse_adr_structure(content)
        except Exception:
            expected_dirs = ["src", "tests", "docs"]
    else:
        expected_dirs = ["src", "tests", "docs"]

    src_dir = root / SRC_DIR
    actual_dirs = []
    if src_dir.exists():
        actual_dirs = [d.name for d in src_dir.iterdir() if d.is_dir() and not d.name.startswith("_")]

    # Top-level dirs
    top_level_actual = [d.name for d in root.iterdir()
                        if d.is_dir() and not d.name.startswith(".") and d.name != "__pycache__"]

    new_dirs = [d for d in top_level_actual if d not in expected_dirs
                and d not in ("node_modules", "venv", ".venv", "dist", "build", ".genesis")]
    missing_dirs = [d for d in expected_dirs if d not in top_level_actual]

    # Check for large growth (compare against a baseline if it exists)
    baseline_file = root / ".genesis" / "structure_baseline.json"
    grown_dirs: list[tuple[str, int, int]] = []

    current_counts = _count_files(src_dir if src_dir.exists() else root)

    if baseline_file.exists():
        import json
        try:
            baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
            for dirname, current_count in current_counts.items():
                prev = baseline.get(dirname, 0)
                if prev > 0 and current_count >= prev * GROWTH_THRESHOLD:
                    grown_dirs.append((dirname, prev, current_count))
        except Exception:
            pass
    else:
        # Save current as baseline
        import json
        baseline_file.parent.mkdir(exist_ok=True)
        baseline_file.write_text(json.dumps(current_counts, indent=2), encoding="utf-8")
        print("  Baseline saved to .genesis/structure_baseline.json")

    return DriftReport(
        new_dirs=new_dirs,
        missing_dirs=missing_dirs,
        grown_dirs=grown_dirs,
        adr_found=adr_found,
    )


def print_report(report: DriftReport, project_path: str = ".") -> None:
    print(f"\nArchitecture Drift Report")
    print(f"Project: {Path(project_path).resolve()}")
    if not report.adr_found:
        print(f"  Note: {ADR_PATH} not found. Using defaults (src, tests, docs).")
    print()

    if not report.new_dirs and not report.missing_dirs and not report.grown_dirs:
        print("  No drift detected. Project structure matches ADR.")
        return

    if report.new_dirs:
        print(f"  New directories (not in ADR): {report.new_dirs}")
        print("  Consider: add to ADR if intentional, or remove if accidental.")

    if report.missing_dirs:
        print(f"  Missing directories (in ADR but not found): {report.missing_dirs}")
        print("  Consider: create them or update ADR to reflect actual structure.")

    if report.grown_dirs:
        for dirname, prev, current in report.grown_dirs:
            print(f"  {dirname}/: grew from {prev} to {current} files (10x threshold)")
        print("  Consider: review whether growth is intentional or represents scope creep.")


def main() -> None:
    project_path = sys.argv[1] if len(sys.argv) > 1 else "."
    report = detect_drift(project_path)
    print_report(report, project_path)
    has_issues = bool(report.new_dirs or report.missing_dirs or report.grown_dirs)
    sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()
