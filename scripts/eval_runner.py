#!/usr/bin/env python3
"""
eval_runner.py - Genesis Architect
Measures trigger rate: how often the skill activates on expected queries vs unexpected ones.
Does not call Claude directly - prints queries for manual or automated testing.

Usage:
  python scripts/eval_runner.py
  python scripts/eval_runner.py --mode print     # print test queries
  python scripts/eval_runner.py --mode report    # show expected pass rates
"""

import json
import sys
import os
import argparse

# Ensure UTF-8 output on all platforms (handles Hebrew and other non-ASCII chars)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


EVAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evals", "test_queries.json")


def load_queries() -> dict:
    with open(EVAL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _split_queries(queries: dict):
    """Return (trigger_list, silent_list) supporting both old and new schema."""
    # New schema: list of {input, should_trigger, expected_flow}
    if "test_cases" in queries:
        cases = queries["test_cases"]
        trigger = [c["input"] for c in cases if c.get("should_trigger")]
        silent = [c["input"] for c in cases if not c.get("should_trigger")]
        return trigger, silent
    # Legacy schema: flat lists
    return queries["should_trigger"], queries["should_not_trigger"]


def print_queries(queries: dict) -> None:
    trigger, silent = _split_queries(queries)
    print("=== Genesis Architect Eval Queries ===\n")
    print("SHOULD TRIGGER (expected: skill activates):")
    for i, q in enumerate(trigger, 1):
        print(f"  {i:2}. {q}")

    print("\nSHOULD NOT TRIGGER (expected: skill stays silent):")
    for i, q in enumerate(silent, 1):
        print(f"  {i:2}. {q}")

    total = len(trigger) + len(silent)
    print(f"\nTotal: {total} queries ({len(trigger)} positive, {len(silent)} negative)")


def print_report(queries: dict) -> None:
    trigger, silent = _split_queries(queries)
    print("=== Eval Report Template ===\n")
    print("Run each query in Claude Code and mark whether the skill triggered.\n")
    print(f"{'#':<4} {'Expected':<12} {'Query':<60} {'Result'}")
    print("-" * 95)

    for i, q in enumerate(trigger, 1):
        print(f"{i:<4} {'TRIGGER':<12} {q[:58]:<60} [ ]")

    offset = len(trigger)
    for i, q in enumerate(silent, 1):
        print(f"{i+offset:<4} {'SILENT':<12} {q[:58]:<60} [ ]")

    total = len(trigger) + len(silent)
    print(f"\nTarget: >90% accuracy ({int(total * 0.9)}/{total} correct)")


def validate_schema(queries: dict) -> int:
    """Validate the schema of the loaded queries. Returns exit code (0 or 1)."""
    errors = []

    if "test_cases" in queries:
        cases = queries["test_cases"]
        if not isinstance(cases, list):
            print("Schema error: 'test_cases' must be a list")
            return 1
        for i, case in enumerate(cases):
            if not isinstance(case.get("input"), str) or not case["input"].strip():
                errors.append(f"  [{i}] 'input' must be a non-empty string")
            if not isinstance(case.get("should_trigger"), bool):
                errors.append(f"  [{i}] 'should_trigger' must be a bool")
            if not isinstance(case.get("expected_flow"), str) or not case["expected_flow"].strip():
                errors.append(f"  [{i}] 'expected_flow' must be a non-empty string")
        if errors:
            print("Schema errors found:")
            for e in errors:
                print(e)
            return 1
        print(f"Schema valid: {len(cases)} test cases")
        return 0

    # Legacy schema
    for key in ("should_trigger", "should_not_trigger"):
        entries = queries.get(key, [])
        if not isinstance(entries, list):
            errors.append(f"  '{key}' must be a list")
            continue
        for i, entry in enumerate(entries):
            if not isinstance(entry, str) or not entry.strip():
                errors.append(f"  '{key}[{i}]' must be a non-empty string")
    if errors:
        print("Schema errors found:")
        for e in errors:
            print(e)
        return 1
    total = len(queries.get("should_trigger", [])) + len(queries.get("should_not_trigger", []))
    print(f"Schema valid: {total} test cases")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Genesis Architect - Eval Runner")
    parser.add_argument("--mode", choices=["print", "report", "validate"], default="print")
    args = parser.parse_args()

    try:
        queries = load_queries()
    except FileNotFoundError:
        print(f"Error: eval file not found at {EVAL_FILE}")
        sys.exit(1)

    if args.mode == "print":
        print_queries(queries)
    elif args.mode == "report":
        print_report(queries)
    elif args.mode == "validate":
        sys.exit(validate_schema(queries))


if __name__ == "__main__":
    main()
