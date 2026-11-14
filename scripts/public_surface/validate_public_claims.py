#!/usr/bin/env python3
"""Fail when public metadata or prose disagrees with data/public-product-facts.json.

Checks (each is named in the output so a clean run states what it covered):
  facts-file     the facts file exists and parses
  versions       manifest.json and plugin.json versions equal the package version
  urls           manifest.json and plugin.json use the canonical repo URL; no stale org
  stale-claims   no tracked reader-facing file states a test count, engine count
                 or score that differs from the facts file
  recover-contract  recover is never described as read-only
  gate-terms     the 14 defined / 9 evaluated gate checks are not called "approval
                 gates" and are never presented as an approval step
  mcp-tools      the public MCP tool count equals the tools the server defines
  guardian       Completion Guardian is described as optional and external
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
APPROVAL_GATES = re.compile(r"approval[- ]gates?", re.I)
SITE_SRC = REPO / "site" / "src"
RECOVER_RO = re.compile(r"recover.*(?:read[- ]only|never writes|does not write)|(?:read[- ]only|never writes|does not write).*recover", re.I)

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

    site_pages = [str(p.relative_to(REPO)) for p in SITE_SRC.rglob("*") if p.suffix in {".md", ".mdx", ".astro"}]
    for rel in list(PROSE) + site_pages:
        path = REPO / rel
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for label, rx, key in CLAIMS:
                for m in rx.finditer(line):
                    if int(m.group(1).replace(",", "")) != facts[key]:
                        errors.append(f"{rel}:{lineno}: {label} {m.group(1)} != {facts[key]}")
    ran.append("stale-claims")

    # recover writes .genesis/ and FRAGILITY_MAP.md, so it is not "read-only".
    recover_scope = list(PROSE) + [
        str(p.relative_to(REPO)) for p in (REPO / "site" / "src").rglob("*") if p.suffix in {".md", ".mdx", ".astro"}
    ] + ["site/content/website-copy.md", "demo/README.md"]
    for rel in recover_scope:
        path = REPO / rel
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if RECOVER_RO.search(line):
                errors.append(f"{rel}:{lineno}: recover is described as read-only; it writes .genesis/ and FRAGILITY_MAP.md")
    ran.append("recover-contract")

    # Gate checks are policy checks, not approvals: "approval gates" is the retired term.
    for rel in list(PROSE) + site_pages + ["pyproject.toml", "manifest.json", "plugin.json"]:
        path = REPO / rel
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if APPROVAL_GATES.search(line):
                errors.append(f"{rel}:{lineno}: 'approval gates' is retired; use 'gate checks' (see ARCHITECTURE_INVARIANTS.json)")
    ran.append("gate-terms")

    # The public MCP tool count must equal what the server really defines.
    sys.path.insert(0, str(REPO / "src"))
    try:
        from genesis_architect.pro.mcp_tools import TOOLS
    except Exception as exc:  # cannot evaluate: report UNKNOWN, never a pass
        errors.append(f"mcp-tools: UNKNOWN, could not import the tool table ({type(exc).__name__})")
    else:
        if len(TOOLS) != facts["mcp_tools"]:
            errors.append(f"mcp-tools: facts say {facts['mcp_tools']}, server defines {len(TOOLS)}")
    ran.append("mcp-tools")

    # Completion Guardian is optional and external: it must not be a counted capability.
    catalog = json.loads((REPO / "data" / "public-capabilities.json").read_text(encoding="utf-8"))
    if "guardian" in json.dumps(catalog.get("capabilities", catalog)).lower().replace("completion_guardian_bridge", ""):
        errors.append("guardian: Completion Guardian appears among counted capabilities; it is an external integration")
    ran.append("guardian")

    print("checks run: " + ", ".join(ran))
    for e in errors:
        print("FAIL " + e, file=sys.stderr)
    if not errors:
        print("public claims match the facts file")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
