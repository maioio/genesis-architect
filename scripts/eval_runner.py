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


EVAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evals", "test_queries.json")


def load_queries() -> dict:
    with open(EVAL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def print_queries(queries: dict) -> None:
    print("=== Genesis Architect Eval Queries ===\n")
    print("SHOULD TRIGGER (expected: skill activates):")
    for i, q in enumerate(queries["should_trigger"], 1):
        print(f"  {i:2}. {q}")

    print("\nSHOULD NOT TRIGGER (expected: skill stays silent):")
    for i, q in enumerate(queries["should_not_trigger"], 1):
        print(f"  {i:2}. {q}")

    total = len(queries["should_trigger"]) + len(queries["should_not_trigger"])
    print(f"\nTotal: {total} queries ({len(queries['should_trigger'])} positive, "
          f"{len(queries['should_not_trigger'])} negative)")


def print_report(queries: dict) -> None:
    print("=== Eval Report Template ===\n")
    print("Run each query in Claude Code and mark whether the skill triggered.\n")
    print(f"{'#':<4} {'Expected':<12} {'Query':<60} {'Result'}")
    print("-" * 95)

    for i, q in enumerate(queries["should_trigger"], 1):
        print(f"{i:<4} {'TRIGGER':<12} {q[:58]:<60} [ ]")

    offset = len(queries["should_trigger"])
    for i, q in enumerate(queries["should_not_trigger"], 1):
        print(f"{i+offset:<4} {'SILENT':<12} {q[:58]:<60} [ ]")

    total = len(queries["should_trigger"]) + len(queries["should_not_trigger"])
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
