#!/usr/bin/env python3
"""Keep the generated blocks in README and the docs in step with the code.

Each block sits between ``<!-- NAME:start -->`` and ``<!-- NAME:end -->`` markers
and is rendered from a generated JSON file, never typed:

    README.md                    facts     <- data/public-product-facts.json
    README.md                    families  <- data/public-capabilities.json
    site/.../architecture.md     numbers   <- data/public-product-facts.json
    site/.../approval-model.md   gates     <- ARCHITECTURE_INVARIANTS.json

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
DOCS = REPO / "site" / "src" / "content" / "docs"
FACTS = REPO / "data" / "public-product-facts.json"
CATALOG = REPO / "data" / "public-capabilities.json"
INVARIANTS = REPO / "ARCHITECTURE_INVARIANTS.json"

GITHUB = "https://github.com/maioio/genesis-architect/blob/main/"
CATALOG_URL = "https://maioio.github.io/genesis-architect/capabilities/"

ACTION = {
    "hard_block": "Hard block: the session stops before any proposed write",
    "block_ask": "Block and ask: the session pauses for your decision",
    "warn": "Warning: reported, the session continues",
}


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def numbers_table(f: dict, link_prefix: str) -> str:
    """Every public number with what it counts. Shared by README and the site."""
    rows = [
        ("Architecture score", f"{f['architecture_score']} / 100",
         "Modularity, coupling, cohesion and layering of this package, scored by its own analyzer"),
        ("Import cycles", str(f["import_cycles"]), "Cycles in this package's import graph"),
        ("Critical anti-patterns", str(f["critical_antipatterns"]),
         "Critical findings from the anti-pattern detector on this package"),
        ("Tests collected", f"{f['tests']:,}", "`pytest --collect-only` on this repository"),
        ("User-facing capabilities", f"{f['capabilities']} in {f['capability_families']} families",
         "Things a person can ask for, from the capability catalog. Workflows and integrations are not counted"),
        ("Top-level commands", str(f["commands"]),
         "`genesis` subcommands, including advanced and legacy ones"),
        ("Registered engines", str(f["engines"]),
         "Units the decision engine schedules. One engine can serve several capabilities"),
        ("Decision modes", str(f["modes"]), "Plans the decision engine can run, such as recovery and research"),
        ("Gate checks", f"{f['gates_active']} evaluated, {f['gates']} defined",
         f"Checks run on a decision session: {f['gates_hard_block']} hard blocks, "
         f"{f['gates_block_ask']} block-and-ask, {f['gates_warn']} warnings"),
        ("Research source registry", f"{f['research_sources']} sources in {f['research_tiers']} tiers",
         "Sources Genesis knows how to classify and rank. Not a list queried on every run"),
        ("MCP tools", f"{f['mcp_tools']} read-only",
         "Analysis tools the Genesis MCP server exposes. They do not write files or use the network"),
    ]
    lines = ["| Number | Value | What it counts |", "|---|---|---|"]
    lines += [f"| {k} | {v} | {m} |" for k, v, m in rows]
    lines += ["", f"Generated for v{f['version']} from "
              f"[`data/public-product-facts.json`]({link_prefix}data/public-product-facts.json)."]
    return "\n".join(lines) + "\n\n"


def families_table(catalog: dict) -> str:
    rows = catalog["capabilities"]
    lines = ["| Family | Capabilities | Includes |", "|---|---|---|"]
    for key, title in catalog["families"].items():
        names = [r["name"] for r in rows if r["family"] == key]
        lines.append(f"| {title} | {len(names)} | {', '.join(names)} |")
    n = catalog["counts"]
    lines += ["", f"{n['capabilities']} capabilities in {n['families']} families. "
              f"The [capability catalog]({CATALOG_URL}) lists each one with its command, "
              "maturity, what it writes and what it needs."]
    return "\n".join(lines) + "\n\n"


def gates_table(inv: dict) -> str:
    gates = inv["gates"]
    b = inv["gate_breakdown"]
    lines = [
        f"{len(gates)} gate checks are defined. {b['evaluated_by_a_mode']} are evaluated by at least one mode; "
        f"the other {len(gates) - b['evaluated_by_a_mode']} are defined in the policy table but no mode "
        "asks for them yet.",
        "",
        "| Check | Fires when | What happens | Can be overridden | Evaluated in modes |",
        "|---|---|---|---|---|",
    ]
    for g in gates:
        modes = ", ".join(g["required_by_modes"]) or "none yet (defined only)"
        lines.append(
            f"| `{g['id']}` | {g['title']} | {ACTION[g['action']]} | "
            f"{'yes' if g['overridable'] else 'no'} | {modes} |"
        )
    lines += ["", "Generated from [`ARCHITECTURE_INVARIANTS.json`]"
              f"({GITHUB}ARCHITECTURE_INVARIANTS.json), which is built from the gate policy table "
              "and the planner."]
    return "\n".join(lines) + "\n\n"


def blocks() -> list[tuple[pathlib.Path, str, str]]:
    facts, catalog, inv = _load(FACTS), _load(CATALOG), _load(INVARIANTS)
    return [
        (README, "facts", numbers_table(facts, "")),
        (README, "families", families_table(catalog)),
        (DOCS / "architecture.md", "numbers", numbers_table(facts, GITHUB)),
        (DOCS / "approval-model.md", "gates", gates_table(inv)),
    ]


def render_files() -> tuple[dict[pathlib.Path, tuple[str, str]], list[str]]:
    """Return {path: (old, new)} and a list of missing-marker errors."""
    files: dict[pathlib.Path, tuple[str, str]] = {}
    errors = []
    for path, name, body in blocks():
        if path not in files:
            text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
            files[path] = (text, text)
        old, cur = files[path]
        pat = re.compile(rf"(<!-- {name}:start -->\n)(.*?)(<!-- {name}:end -->)", re.S)
        if not pat.search(cur):
            errors.append(f"{path.relative_to(REPO)} has no {name} markers")
            continue
        files[path] = (old, pat.sub(lambda m, b=body: m.group(1) + b + m.group(3), cur))
    return files, errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    files, errors = render_files()
    for e in errors:
        print(e, file=sys.stderr)
    if errors:
        return 1
    if args.write:
        for path, (_, new) in files.items():
            path.write_text(new, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(REPO)}")
        return 0
    stale = [p for p, (old, new) in files.items() if old != new]
    for p in stale:
        print(f"STALE: generated block in {p.relative_to(REPO)} disagrees with its source.\n"
              "       Run: python scripts/public_surface/sync_readme_facts.py --write", file=sys.stderr)
    if not stale:
        print("generated blocks match their sources: " + ", ".join(f"{p.name}:{n}" for p, n, _ in blocks()))
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
