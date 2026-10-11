#!/usr/bin/env python3
"""Keep the README facts block in step with data/public-product-facts.json.

The block between the facts markers is rendered from the JSON, never typed.

    python scripts/public_surface/sync_readme_facts.py --write
    python scripts/public_surface/sync_readme_facts.py --check   # exit 1 if stale
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
README = REPO / "README.md"
FACTS = REPO / "data" / "public-product-facts.json"
BLOCK = re.compile(r"(<!-- facts:start -->\n)(.*?)(<!-- facts:end -->)", re.S)


def render(facts: dict) -> str:
    rows = [
        ("Architecture score", f"{facts['architecture_score']} / 100"),
        ("Import cycles", str(facts["import_cycles"])),
        ("Critical anti-patterns", str(facts["critical_antipatterns"])),
        ("Tests collected", f"{facts['tests']:,}"),
        ("Engines / approval gates", f"{facts['engines']} / {facts['gates']}"),
        ("Mapped capabilities / commands", f"{facts['capabilities']} / {facts['commands']}"),
    ]
    lines = ["| Measured on this repository | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    lines.append("")
    lines.append(f"Generated for v{facts['version']} from "
                 "[`data/public-product-facts.json`](data/public-product-facts.json).")
    return "\n".join(lines) + "\n\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    text = README.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not BLOCK.search(text):
        print("README.md has no facts markers", file=sys.stderr)
        return 1
    new = BLOCK.sub(lambda m: m.group(1) + render(facts) + m.group(3), text)
    if args.write:
        README.write_text(new, encoding="utf-8", newline="\n")
        print("README facts block written")
        return 0
    if new != text:
        print("STALE: README facts block disagrees with data/public-product-facts.json.\n"
              "       Run: python scripts/public_surface/sync_readme_facts.py --write", file=sys.stderr)
        return 1
    print("README facts block matches the facts file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
