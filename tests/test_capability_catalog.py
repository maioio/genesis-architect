"""Drift guards for the public capability catalog.

Chain: capability_map -> capability_catalog -> data/public-capabilities.json ->
docs/capabilities.md. Each test names the file to fix when it fails.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

from genesis_architect.pro import capability_catalog as cat
from genesis_architect.pro.capability_map import CAPABILITIES
from genesis_architect.pro.commands.parser import _build_parser

REPO = pathlib.Path(__file__).resolve().parents[1]


def _argparse_commands() -> set[str]:
    parser = _build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    raise AssertionError("argparse parser has no subcommands")


def _typer_commands() -> set[str]:
    from genesis_architect.cli import app

    return {c.name or (c.callback.__name__ if c.callback else "") for c in app.registered_commands}


def test_meta_covers_every_mapped_capability():
    rows = cat.build_catalog()  # raises with the exact module names on drift
    assert len(rows) == len(CAPABILITIES)


def test_every_meta_value_is_in_the_vocabulary():
    for module, m in cat.META.items():
        assert m.family in cat.FAMILIES, f"{module}: unknown family {m.family!r}"
        assert m.maturity in {"stable", "optional", "experimental"}, f"{module}: maturity {m.maturity!r}"
        assert m.writes in {"none", "state", "project"}, f"{module}: writes {m.writes!r}"
        assert m.network in {"none", "optional", "required"}, f"{module}: network {m.network!r}"
        assert m.llm in {"no", "optional", "required"}, f"{module}: llm {m.llm!r}"


def test_every_family_is_used():
    used = {m.family for m in cat.META.values()}
    assert used == set(cat.FAMILIES), f"empty families: {sorted(set(cat.FAMILIES) - used)}"


def test_commands_match_the_real_cli():
    listed = {c.name for c in cat.COMMANDS}
    real = _argparse_commands() | _typer_commands()
    assert listed == real, (
        f"capability_catalog.COMMANDS is out of sync with the CLI. "
        f"Unlisted real commands: {sorted(real - listed)}; listed but not real: {sorted(listed - real)}."
    )


def test_command_status_vocabulary():
    for c in cat.COMMANDS:
        assert c.status in {"PUBLIC", "ADVANCED", "LEGACY", "DEPRECATED"}, f"{c.name}: {c.status}"


def test_generated_files_are_current():
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts/public_surface/generate_capability_catalog.py"), "--check"],
        capture_output=True, text=True, cwd=REPO, check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_json_counts_match_catalog():
    data = json.loads((REPO / "data/public-capabilities.json").read_text(encoding="utf-8"))
    assert data["counts"]["capabilities"] == len(CAPABILITIES)
    assert len(data["capabilities"]) == len(CAPABILITIES)
    facts = json.loads((REPO / "data/public-product-facts.json").read_text(encoding="utf-8"))
    assert facts["capabilities"] == data["counts"]["capabilities"]
    assert facts["commands"] == data["counts"]["commands"]


def test_commands_page_mentions_every_command():
    page = (REPO / "site/src/content/docs/commands.md").read_text(encoding="utf-8")
    missing = [c.name for c in cat.COMMANDS if f"`{c.name}" not in page]
    assert not missing, f"site/src/content/docs/commands.md does not document: {missing}"


def test_readme_names_every_family():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    missing = [t for t in cat.FAMILIES.values() if t not in readme]
    assert not missing, f"README.md capability table is missing families: {missing}"
