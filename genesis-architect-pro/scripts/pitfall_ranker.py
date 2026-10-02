"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/pitfall_ranker.py instead."""
import sys
import json
from genesis_architect.core.pitfall_ranker import (
    RankedPitfall,
    from_exa_result,
    rank,
    format_ranked,
)

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: pitfall_ranker.py rank <json_file>")
        print("  json_file: list of {title, url, source, confidence, signal_type, raw_text, engagement, days_old}")
        sys.exit(1)

    if args[0] == "rank" and len(args) >= 2:
        raw = json.loads(__import__("pathlib").Path(args[1]).read_text(encoding="utf-8"))
        pitfalls = [RankedPitfall(**p) for p in raw]
        ranked = rank(pitfalls)
        print(format_ranked(ranked))
    else:
        print(f"Unknown command: {args[0]}")
        sys.exit(1)
