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


def main():
    parser = argparse.ArgumentParser(description="Genesis Architect - Eval Runner")
    parser.add_argument("--mode", choices=["print", "report"], default="print")
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


if __name__ == "__main__":
    main()
