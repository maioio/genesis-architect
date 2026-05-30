#!/usr/bin/env python3
"""Genesis state file helpers - replaces prose hard gates with machine-readable state."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def genesis_dir(project_dir: str) -> Path:
    return Path(project_dir) / ".genesis"


# ---------------------------------------------------------------------------
# Phase 2 gate: repo floor (12 repos verified, 5-8 deep)
# ---------------------------------------------------------------------------

def write_phase2(project_dir: str, repo_count: int, deep_count: int,
                 override: bool = False) -> int:
    d = genesis_dir(project_dir)
    d.mkdir(parents=True, exist_ok=True)
    passed = repo_count >= 12 and deep_count >= 5
    state = {
        "repo_count": repo_count,
        "deep_count": deep_count,
        "phase2_passed": passed,
        "user_override": override,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    (d / "phase-2-research.json").write_text(json.dumps(state, indent=2))
    if not passed and not override:
        print(
            f"ERROR: Phase 2 floor not met: {repo_count} repos (need 12), "
            f"{deep_count} deep (need 5). Use --override to accept thin research.",
            file=sys.stderr,
        )
        return 1
    label = "OVERRIDE" if override else "PASSED"
    print(f"Phase 2 [{label}]: repos={repo_count} deep={deep_count}")
    return 0


def require_phase2(project_dir: str) -> int:
    path = genesis_dir(project_dir) / "phase-2-research.json"
    if not path.exists():
        print(f"ERROR: {path} not found - Phase 2 not recorded", file=sys.stderr)
        return 1
    state = json.loads(path.read_text())
    if not state.get("phase2_passed") and not state.get("user_override"):
        print(
            f"ERROR: Phase 2 gate not satisfied "
            f"(repos={state.get('repo_count')}, deep={state.get('deep_count')}). "
            f"Collect more repos or re-run with --override to accept thin research.",
            file=sys.stderr,
        )
        return 1
    label = "override accepted" if state.get("user_override") else "passed"
    print(
        f"Phase 2 {label}: repos={state.get('repo_count')} "
        f"deep={state.get('deep_count')} at {state.get('timestamp')}"
    )
    return 0


# ---------------------------------------------------------------------------
# Evidence pack gate: ARCHITECTURE_EVIDENCE.md generated before Phase 6
# ---------------------------------------------------------------------------

def write_evidence_pack(project_dir: str, pitfall_count: int,
                        mapped_count: int) -> int:
    d = genesis_dir(project_dir)
    d.mkdir(parents=True, exist_ok=True)
    base = Path(project_dir)
    evidence_md = base / "ARCHITECTURE_EVIDENCE.md"
    evidence_json = d / "evidence.json"

    if not evidence_md.exists():
        print(
            f"ERROR: ARCHITECTURE_EVIDENCE.md not found in {base}. "
            "Run: python scripts/evidence_pack.py generate --project-dir .",
            file=sys.stderr,
        )
        return 1
    if not evidence_json.exists():
        print(
            "ERROR: .genesis/evidence.json not found. "
            "Run: python scripts/evidence_pack.py generate --project-dir .",
            file=sys.stderr,
        )
        return 1

    unmapped = pitfall_count - mapped_count
    passed = unmapped == 0
    state = {
        "pitfall_count": pitfall_count,
        "mapped_count": mapped_count,
        "unmapped_count": unmapped,
        "evidence_pack_passed": passed,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    (d / "evidence-pack.json").write_text(json.dumps(state, indent=2))
    if not passed:
        print(
            f"ERROR: Evidence pack incomplete: {unmapped} pitfall(s) have no "
            "mitigation_file_path. Fix PITFALLS.md, re-run generate, then retry.",
            file=sys.stderr,
        )
        return 1
    print(
        f"Evidence pack gate: PASSED ({pitfall_count} pitfalls, all mapped)"
    )
    return 0


def require_evidence_pack(project_dir: str) -> int:
    base = Path(project_dir)
    evidence_md = base / "ARCHITECTURE_EVIDENCE.md"
    d = genesis_dir(project_dir)
    gate_path = d / "evidence-pack.json"

    if not evidence_md.exists():
        print(
            "ERROR: ARCHITECTURE_EVIDENCE.md not found - Phase 6 is blocked. "
            "Run: python scripts/evidence_pack.py generate --project-dir .",
            file=sys.stderr,
        )
        return 1
    if not gate_path.exists():
        print(
            "ERROR: .genesis/evidence-pack.json not found - Phase 6 is blocked. "
            "Run: python scripts/evidence_pack.py generate --project-dir . "
            "then: python scripts/genesis_state.py write-evidence-pack .",
            file=sys.stderr,
        )
        return 1
    state = json.loads(gate_path.read_text())
    if not state.get("evidence_pack_passed"):
        unmapped = state.get("unmapped_count", "?")
        print(
            f"ERROR: Evidence pack gate not satisfied ({unmapped} unmapped pitfall(s)). "
            "Fix PITFALLS.md mitigation_file_path fields and re-generate.",
            file=sys.stderr,
        )
        return 1
    print(
        f"Evidence pack: satisfied at {state.get('timestamp')} "
        f"({state.get('pitfall_count')} pitfalls, all mapped)"
    )
    return 0


# ---------------------------------------------------------------------------
# Phase 3 gate: research_validator citation check passed
# ---------------------------------------------------------------------------

def write_phase3_validation(project_dir: str, urls_checked: int,
                            urls_dead: int = 0) -> int:
    d = genesis_dir(project_dir)
    d.mkdir(parents=True, exist_ok=True)
    passed = urls_dead == 0
    state = {
        "urls_checked": urls_checked,
        "urls_dead": urls_dead,
        "phase3_validation_passed": passed,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    (d / "phase-3-validation.json").write_text(json.dumps(state, indent=2))
    if not passed:
        print(
            f"ERROR: Phase 3 validation failed: {urls_dead} dead URL(s) among "
            f"{urls_checked} checked. Fix or drop affected repos before Phase 3.",
            file=sys.stderr,
        )
        return 1
    print(f"Phase 3 validation passed: {urls_checked} URL(s) checked, 0 dead")
    return 0


def require_phase3_validation(project_dir: str) -> int:
    path = genesis_dir(project_dir) / "phase-3-validation.json"
    if not path.exists():
        print(f"ERROR: {path} not found - Phase 3 validation not recorded", file=sys.stderr)
        return 1
    state = json.loads(path.read_text())
    if not state.get("phase3_validation_passed"):
        print(
            f"ERROR: Phase 3 validation gate not satisfied "
            f"({state.get('urls_dead')} dead URL(s)). "
            "Re-run research_validator.py --verify-issues and fix dead citations.",
            file=sys.stderr,
        )
        return 1
    print(f"Phase 3 validation satisfied at {state.get('timestamp')}")
    return 0


# ---------------------------------------------------------------------------
# Phase 5 gate: three doc previews must be present
# ---------------------------------------------------------------------------

def write_phase5_previews(project_dir: str, research_present: bool,
                          pitfalls_present: bool, roadmap_present: bool) -> int:
    d = genesis_dir(project_dir)
    d.mkdir(parents=True, exist_ok=True)
    all_present = research_present and pitfalls_present and roadmap_present
    state = {
        "research_present": research_present,
        "pitfalls_present": pitfalls_present,
        "roadmap_present": roadmap_present,
        "phase5_previews_present": all_present,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    (d / "phase-5-previews.json").write_text(json.dumps(state, indent=2))
    if not all_present:
        missing = [k for k, v in {
            "RESEARCH.md": research_present,
            "PITFALLS.md": pitfalls_present,
            "ROADMAP.md": roadmap_present,
        }.items() if not v]
        print(
            f"ERROR: Phase 5 previews incomplete - missing: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1
    print("Phase 5 previews: all three docs present")
    return 0


def require_phase5_previews(project_dir: str) -> int:
    path = genesis_dir(project_dir) / "phase-5-previews.json"
    if not path.exists():
        print(f"ERROR: {path} not found - Phase 5 previews not recorded", file=sys.stderr)
        return 1
    state = json.loads(path.read_text())
    if not state.get("phase5_previews_present"):
        missing = [k for k, v in {
            "RESEARCH.md": state.get("research_present"),
            "PITFALLS.md": state.get("pitfalls_present"),
            "ROADMAP.md": state.get("roadmap_present"),
        }.items() if not v]
        print(
            f"ERROR: Phase 5 previews gate not satisfied - missing: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1
    print(f"Phase 5 previews satisfied at {state.get('timestamp')}")
    return 0


# ---------------------------------------------------------------------------
# Phase 5 choice gate (was write_phase5)
# ---------------------------------------------------------------------------

def write_phase5(project_dir: str, archetype: str, tier: str, language: str, choice: str) -> int:
    d = genesis_dir(project_dir)
    d.mkdir(parents=True, exist_ok=True)
    state = {
        "archetype": archetype,
        "tier": tier,
        "language": language,
        "user_choice": choice,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    (d / "phase-5-confirmed.json").write_text(json.dumps(state, indent=2))
    print(f"phase-5-confirmed.json written to {d}")
    return 0


def require_phase5(project_dir: str) -> int:
    path = genesis_dir(project_dir) / "phase-5-confirmed.json"
    if not path.exists():
        print(f"ERROR: {path} not found - Phase 5 not confirmed", file=sys.stderr)
        return 1
    state = json.loads(path.read_text())
    if not state.get("user_choice"):
        print("ERROR: user_choice is null in phase-5-confirmed.json", file=sys.stderr)
        return 1
    print(f"Phase 5 confirmed: archetype={state['archetype']} tier={state['tier']} "
          f"language={state['language']} choice={state['user_choice']} at {state['timestamp']}")
    return 0


# ---------------------------------------------------------------------------
# Phase 6 smoke-test gate
# ---------------------------------------------------------------------------

SMOKE_COMMANDS: dict[str, str] = {
    "cli":     "{entrypoint} --version",
    "library": "python -c \"import {pkg}; print({pkg}.__version__)\"",
    "service": "curl -sf http://localhost:{port}/health",
    "frontend": "npm run build",
}


def write_phase6_smoke(project_dir: str, archetype: str, smoke_command: str,
                       exit_code: int) -> int:
    d = genesis_dir(project_dir)
    d.mkdir(parents=True, exist_ok=True)
    passed = exit_code == 0
    state = {
        "archetype": archetype,
        "smoke_command": smoke_command,
        "exit_code": exit_code,
        "phase6_smoke_defined": True,
        "phase6_smoke_passed": passed,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    (d / "phase-6-smoke.json").write_text(json.dumps(state, indent=2))
    if not passed:
        print(
            f"ERROR: Smoke test failed (exit {exit_code}): {smoke_command}",
            file=sys.stderr,
        )
        return 1
    print(f"Phase 6 smoke passed: {smoke_command}")
    return 0


def require_phase6_smoke(project_dir: str) -> int:
    path = genesis_dir(project_dir) / "phase-6-smoke.json"
    if not path.exists():
        print(f"ERROR: {path} not found - Phase 6 smoke test not recorded", file=sys.stderr)
        return 1
    state = json.loads(path.read_text())
    if not state.get("phase6_smoke_defined"):
        print("ERROR: phase6_smoke_defined is false in phase-6-smoke.json", file=sys.stderr)
        return 1
    if not state.get("phase6_smoke_passed"):
        print(
            f"ERROR: Smoke test did not pass (exit {state.get('exit_code')}): "
            f"{state.get('smoke_command')}",
            file=sys.stderr,
        )
        return 1
    print(
        f"Phase 6 smoke satisfied: {state.get('smoke_command')} "
        f"at {state.get('timestamp')}"
    )
    return 0


# ---------------------------------------------------------------------------
# Tests passing gate (unchanged)
# ---------------------------------------------------------------------------

def write_tests_passing(project_dir: str) -> int:
    d = genesis_dir(project_dir)
    d.mkdir(parents=True, exist_ok=True)
    state = {"exit_code": 0, "timestamp": datetime.now(UTC).isoformat()}
    (d / "tests-passing.json").write_text(json.dumps(state, indent=2))
    print(f"tests-passing.json written to {d}")
    return 0


def require_tests_passing(project_dir: str) -> int:
    path = genesis_dir(project_dir) / "tests-passing.json"
    if not path.exists():
        print(f"ERROR: {path} not found - tests-passing gate not satisfied", file=sys.stderr)
        return 1
    state = json.loads(path.read_text())
    if state.get("exit_code") != 0:
        print(f"ERROR: exit_code={state.get('exit_code')} in tests-passing.json", file=sys.stderr)
        return 1
    print(f"Tests passing: exit_code=0 at {state['timestamp']}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Genesis state file helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    # write-evidence-pack
    epw = sub.add_parser("write-evidence-pack")
    epw.add_argument("project_dir")
    epw.add_argument("--pitfall-count", type=int, required=True)
    epw.add_argument("--mapped-count", type=int, required=True)

    # require-evidence-pack
    epr = sub.add_parser("require-evidence-pack")
    epr.add_argument("project_dir")

    # write-phase3-validation
    p3w = sub.add_parser("write-phase3-validation")
    p3w.add_argument("project_dir")
    p3w.add_argument("--urls-checked", type=int, required=True)
    p3w.add_argument("--urls-dead", type=int, default=0)

    # require-phase3-validation
    p3r = sub.add_parser("require-phase3-validation")
    p3r.add_argument("project_dir")

    # write-phase2
    p2w = sub.add_parser("write-phase2")
    p2w.add_argument("project_dir")
    p2w.add_argument("--repo-count", type=int, required=True)
    p2w.add_argument("--deep-count", type=int, required=True)
    p2w.add_argument("--override", action="store_true",
                     help="Accept thin research (records user acknowledgment)")

    # require-phase2
    p2r = sub.add_parser("require-phase2")
    p2r.add_argument("project_dir")

    # write-phase5-previews
    p5pw = sub.add_parser("write-phase5-previews")
    p5pw.add_argument("project_dir")
    p5pw.add_argument("--research", action="store_true")
    p5pw.add_argument("--pitfalls", action="store_true")
    p5pw.add_argument("--roadmap", action="store_true")

    # require-phase5-previews
    p5pr = sub.add_parser("require-phase5-previews")
    p5pr.add_argument("project_dir")

    # write-phase5 (choice gate)
    p5w = sub.add_parser("write-phase5")
    p5w.add_argument("project_dir")
    p5w.add_argument("--archetype", required=True)
    p5w.add_argument("--tier", required=True)
    p5w.add_argument("--language", required=True)
    p5w.add_argument("--choice", required=True)

    # require-phase5
    p5r = sub.add_parser("require-phase5")
    p5r.add_argument("project_dir")

    # write-phase6-smoke
    p6sw = sub.add_parser("write-phase6-smoke")
    p6sw.add_argument("project_dir")
    p6sw.add_argument("--archetype", required=True)
    p6sw.add_argument("--smoke-command", required=True)
    p6sw.add_argument("--exit-code", type=int, required=True)

    # require-phase6-smoke
    p6sr = sub.add_parser("require-phase6-smoke")
    p6sr.add_argument("project_dir")

    # write-tests-passing
    tpw = sub.add_parser("write-tests-passing")
    tpw.add_argument("project_dir")

    # require-tests-passing
    tpr = sub.add_parser("require-tests-passing")
    tpr.add_argument("project_dir")

    args = parser.parse_args()

    if args.command == "write-evidence-pack":
        sys.exit(write_evidence_pack(args.project_dir, args.pitfall_count, args.mapped_count))
    elif args.command == "require-evidence-pack":
        sys.exit(require_evidence_pack(args.project_dir))
    elif args.command == "write-phase3-validation":
        sys.exit(write_phase3_validation(args.project_dir, args.urls_checked, args.urls_dead))
    elif args.command == "require-phase3-validation":
        sys.exit(require_phase3_validation(args.project_dir))
    elif args.command == "write-phase2":
        sys.exit(write_phase2(args.project_dir, args.repo_count, args.deep_count, args.override))
    elif args.command == "require-phase2":
        sys.exit(require_phase2(args.project_dir))
    elif args.command == "write-phase5-previews":
        sys.exit(write_phase5_previews(
            args.project_dir, args.research, args.pitfalls, args.roadmap
        ))
    elif args.command == "require-phase5-previews":
        sys.exit(require_phase5_previews(args.project_dir))
    elif args.command == "write-phase5":
        sys.exit(write_phase5(args.project_dir, args.archetype, args.tier, args.language, args.choice))
    elif args.command == "require-phase5":
        sys.exit(require_phase5(args.project_dir))
    elif args.command == "write-phase6-smoke":
        sys.exit(write_phase6_smoke(
            args.project_dir, args.archetype, args.smoke_command, args.exit_code
        ))
    elif args.command == "require-phase6-smoke":
        sys.exit(require_phase6_smoke(args.project_dir))
    elif args.command == "write-tests-passing":
        sys.exit(write_tests_passing(args.project_dir))
    elif args.command == "require-tests-passing":
        sys.exit(require_tests_passing(args.project_dir))


if __name__ == "__main__":
    main()
