#!/usr/bin/env python3
"""Genesis state file helpers - replaces prose hard gates with machine-readable state."""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone


def genesis_dir(project_dir: str) -> Path:
    return Path(project_dir) / ".genesis"


def write_phase5(project_dir: str, archetype: str, tier: str, language: str, choice: str) -> int:
    d = genesis_dir(project_dir)
    d.mkdir(parents=True, exist_ok=True)
    state = {
        "archetype": archetype,
        "tier": tier,
        "language": language,
        "user_choice": choice,
        "timestamp": datetime.now(timezone.utc).isoformat(),
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


def write_tests_passing(project_dir: str) -> int:
    d = genesis_dir(project_dir)
    d.mkdir(parents=True, exist_ok=True)
    state = {"exit_code": 0, "timestamp": datetime.now(timezone.utc).isoformat()}
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


def main():
    parser = argparse.ArgumentParser(description="Genesis state file helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    p5w = sub.add_parser("write-phase5")
    p5w.add_argument("project_dir")
    p5w.add_argument("--archetype", required=True)
    p5w.add_argument("--tier", required=True)
    p5w.add_argument("--language", required=True)
    p5w.add_argument("--choice", required=True)

    p5r = sub.add_parser("require-phase5")
    p5r.add_argument("project_dir")

    tpw = sub.add_parser("write-tests-passing")
    tpw.add_argument("project_dir")

    tpr = sub.add_parser("require-tests-passing")
    tpr.add_argument("project_dir")

    args = parser.parse_args()

    if args.command == "write-phase5":
        sys.exit(write_phase5(args.project_dir, args.archetype, args.tier, args.language, args.choice))
    elif args.command == "require-phase5":
        sys.exit(require_phase5(args.project_dir))
    elif args.command == "write-tests-passing":
        sys.exit(write_tests_passing(args.project_dir))
    elif args.command == "require-tests-passing":
        sys.exit(require_tests_passing(args.project_dir))


if __name__ == "__main__":
    main()
