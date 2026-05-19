#!/usr/bin/env python3
"""
mitigation_enforcer.py - Genesis Architect v2.5.0

Hard enforcement of mitigation_file_path rules from PITFALLS.md.

Unlike pitfall_coverage_check.py (which does keyword grepping and is advisory),
this script checks that the EXACT FILE specified in mitigation_file_path actually
exists in the project tree. A missing file means the mitigation was never
implemented. Exit 1 is a hard block - not a warning.

Usage:
    python scripts/mitigation_enforcer.py PITFALLS.md --src-root src/
    python scripts/mitigation_enforcer.py PITFALLS.md --src-root src/ --json

Reads .genesis/evidence.json if present (richer data). Falls back to parsing
PITFALLS.md directly if not.

Exit codes:
    0 - all mitigation_file_paths exist
    1 - one or more are missing (enforcement failure)
    2 - bad arguments or unreadable files
"""

import json
import re
import sys
import argparse
from pathlib import Path


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_pitfalls_from_md(pitfalls_path: Path) -> list[dict]:
    """
    Parse pitfalls directly from PITFALLS.md.
    Returns list of {id, name, mitigation_file_path, issue_url}.
    """
    text = pitfalls_path.read_text(encoding="utf-8")
    pitfalls: list[dict] = []

    sections = re.split(r"(?m)^## (Pitfall \d+[^\n]*)\n", text)
    for i in range(1, len(sections), 2):
        header = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""

        num_m = re.search(r"Pitfall\s+(\d+)", header, re.IGNORECASE)
        pid = f"pitfall_{num_m.group(1)}" if num_m else f"pitfall_{(i+1)//2}"
        name = re.sub(r"^Pitfall\s+\d+[:\s]*", "", header, flags=re.IGNORECASE).strip()

        path_m = re.search(r"mitigation_file_path\s*:\s*([^\n]+)", body)
        url_m = re.search(r"https://github\.com/[^\s,)\]>\"']+/issues/\d+", body)

        pitfalls.append({
            "id": pid,
            "name": name,
            "mitigation_file_path": path_m.group(1).strip() if path_m else "",
            "issue_url": url_m.group(0) if url_m else "",
        })

    return pitfalls


def _load_from_evidence(evidence_json: Path) -> list[dict]:
    """Load pitfall list from .genesis/evidence.json if present."""
    if not evidence_json.exists():
        return []
    try:
        data = json.loads(evidence_json.read_text(encoding="utf-8"))
        return data.get("pitfalls", [])
    except (json.JSONDecodeError, OSError):
        return []


# ---------------------------------------------------------------------------
# Core enforcement logic
# ---------------------------------------------------------------------------

def _resolve_mitigation_path(raw_path: str, project_root: Path) -> Path | None:
    """
    Resolve a mitigation_file_path relative to project_root.
    Returns the Path if it exists, None otherwise.

    The path in PITFALLS.md is always written relative to the project root
    (e.g., 'src/myapp/utils/security.py'), never absolute.
    """
    if not raw_path:
        return None
    candidate = (project_root / raw_path).resolve()
    # Security: must stay inside project root
    try:
        candidate.relative_to(project_root.resolve())
    except ValueError:
        return None
    return candidate if candidate.exists() else None


class EnforcementResult:
    def __init__(self) -> None:
        self.passed: list[dict] = []
        self.failed: list[dict] = []
        self.unmapped: list[dict] = []

    @property
    def ok(self) -> bool:
        return not self.failed and not self.unmapped

    def summary(self) -> str:
        total = len(self.passed) + len(self.failed) + len(self.unmapped)
        return (
            f"Mitigations: {len(self.passed)}/{total} present | "
            f"missing: {len(self.failed)} | unmapped: {len(self.unmapped)}"
        )


def enforce(
    pitfalls: list[dict],
    project_root: Path,
) -> EnforcementResult:
    """
    For each pitfall, verify that mitigation_file_path exists.

    Pitfalls with no mitigation_file_path are flagged as 'unmapped' -
    this is a separate failure category from a mapped path that doesn't exist.
    """
    result = EnforcementResult()

    for p in pitfalls:
        pid = p.get("id", "?")
        name = p.get("name", "?")
        raw_path = p.get("mitigation_file_path", "").strip()

        if not raw_path:
            result.unmapped.append({
                "id": pid,
                "name": name,
                "reason": "No mitigation_file_path in PITFALLS.md - add one before Phase 6",
            })
            continue

        resolved = _resolve_mitigation_path(raw_path, project_root)
        if resolved is None:
            result.failed.append({
                "id": pid,
                "name": name,
                "mitigation_file_path": raw_path,
                "reason": f"File not found: {raw_path}",
            })
        else:
            result.passed.append({
                "id": pid,
                "name": name,
                "mitigation_file_path": raw_path,
                "resolved": str(resolved),
            })

    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _print_report(result: EnforcementResult, as_json: bool) -> None:
    if as_json:
        print(json.dumps({
            "passed": result.passed,
            "failed": result.failed,
            "unmapped": result.unmapped,
            "ok": result.ok,
            "summary": result.summary(),
        }, indent=2))
        return

    print(result.summary(), file=sys.stderr)
    for p in result.passed:
        print(f"  [OK]      {p['id']}: {p['mitigation_file_path']}", file=sys.stderr)
    for f in result.failed:
        print(f"  [MISSING] {f['id']}: {f['mitigation_file_path']}", file=sys.stderr)
        print(f"            {f['reason']}", file=sys.stderr)
    for u in result.unmapped:
        print(f"  [UNMAPPED]{u['id']}: {u['name']}", file=sys.stderr)
        print(f"            {u['reason']}", file=sys.stderr)


def _print_failure_guidance(result: EnforcementResult) -> None:
    """Print actionable fix instructions on failure."""
    if result.failed:
        print("\nFix required:", file=sys.stderr)
        for f in result.failed:
            print(
                f"  Create '{f['mitigation_file_path']}' with the mitigation code for {f['id']}.",
                file=sys.stderr,
            )
    if result.unmapped:
        print("\nAdd mitigation_file_path to these pitfalls in PITFALLS.md:", file=sys.stderr)
        for u in result.unmapped:
            print(f"  ## {u['name']}", file=sys.stderr)
            print(f"  mitigation_file_path: src/<package>/utils/<module>.py", file=sys.stderr)
    print(
        "\nRe-run after fixing:\n"
        "  python scripts/mitigation_enforcer.py PITFALLS.md --src-root src/",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genesis Architect - Mitigation Enforcer\n"
                    "Hard-checks that every mitigation_file_path in PITFALLS.md exists.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "pitfalls_md",
        help="Path to PITFALLS.md",
    )
    parser.add_argument(
        "--src-root",
        default=".",
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of human-readable text",
    )
    parser.add_argument(
        "--from-evidence",
        action="store_true",
        help="Load pitfalls from .genesis/evidence.json instead of parsing PITFALLS.md",
    )

    args = parser.parse_args()

    pitfalls_path = Path(args.pitfalls_md)
    project_root = Path(args.src_root).resolve()

    if not pitfalls_path.exists():
        print(f"ERROR: {pitfalls_path} not found", file=sys.stderr)
        sys.exit(2)
    if not project_root.is_dir():
        print(f"ERROR: --src-root {project_root} is not a directory", file=sys.stderr)
        sys.exit(2)

    # Load pitfall list
    if args.from_evidence:
        evidence_json = project_root / ".genesis" / "evidence.json"
        pitfalls = _load_from_evidence(evidence_json)
        if not pitfalls:
            print(
                "WARNING: --from-evidence specified but .genesis/evidence.json is missing "
                "or has no pitfalls. Falling back to PITFALLS.md parser.",
                file=sys.stderr,
            )
            pitfalls = _parse_pitfalls_from_md(pitfalls_path)
    else:
        pitfalls = _parse_pitfalls_from_md(pitfalls_path)

    if not pitfalls:
        print("WARNING: No pitfalls parsed from PITFALLS.md", file=sys.stderr)
        sys.exit(0)

    result = enforce(pitfalls, project_root)
    _print_report(result, as_json=args.json)

    if not result.ok:
        _print_failure_guidance(result)
        sys.exit(1)

    if not args.json:
        print("Mitigation enforcement: PASSED", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
