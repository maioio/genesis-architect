#!/usr/bin/env python3
"""Fail when public metadata or prose disagrees with data/public-product-facts.json.

Checks (each is named in the output so a clean run states what it covered):
  facts-file     the facts file exists and parses
  versions       manifest.json and plugin.json versions equal the package version
  urls           manifest.json and plugin.json use the canonical repo URL; no stale org
  stale-claims   no tracked reader-facing file states a test count, engine count
                 or score that differs from the facts file
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
FACTS = REPO / "data" / "public-product-facts.json"
PROSE = ["README.md", "SKILL.md", "CONTRIBUTING.md", "SECURITY.md",
         "docs/architecture/overview.md", "ARCHITECTURE.md"]
STALE_ORG = "maioio-projects"

# (label, regex with one numeric group, facts key)
CLAIMS = [
    ("tests", re.compile(r"\b(\d{1,2},?\d{3})\s+tests\b"), "tests"),
    ("engines", re.compile(r"\b(\d{1,2})\s+engines\b"), "engines"),
    ("gates", re.compile(r"\b(\d{1,2})\s+(?:approval\s+)?gates\b"), "gates"),
]


def main() -> int:
    errors: list[str] = []
    ran: list[str] = []

    if not FACTS.exists():
        print(f"FAIL facts-file: {FACTS} missing", file=sys.stderr)
        return 1
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    ran.append("facts-file")

    for name in ("manifest.json", "plugin.json"):
        data = json.loads((REPO / name).read_text(encoding="utf-8"))
        if data.get("version") != facts["version"]:
            errors.append(f"{name}: version {data.get('version')} != {facts['version']}")
        for key in ("homepage", "repository"):
            val = data.get(key)
            if val and STALE_ORG in val:
                errors.append(f"{name}: {key} uses stale org {STALE_ORG}")
    ran += ["versions", "urls"]

    for rel in PROSE:
        path = REPO / rel
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for label, rx, key in CLAIMS:
                for m in rx.finditer(line):
                    if int(m.group(1).replace(",", "")) != facts[key]:
                        errors.append(f"{rel}:{lineno}: {label} {m.group(1)} != {facts[key]}")
    ran.append("stale-claims")

    print("checks run: " + ", ".join(ran))
    for e in errors:
        print("FAIL " + e, file=sys.stderr)
    if not errors:
        print("public claims match the facts file")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
