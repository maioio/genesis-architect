"""Concept guards for the public surface.

These tests protect ideas, not sentences: what is counted, what is not, and which
canonical file a public claim must trace back to. Each assertion names the file to fix.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
DOCS = REPO / "site" / "src" / "content" / "docs"

pytestmark = pytest.mark.skipif(
    not (REPO / "data" / "public-capabilities.json").exists() or not DOCS.exists(),
    reason="generated public files absent (container image); enforced by the Public Surface workflow",
)


def _json(rel: str) -> dict:
    return json.loads((REPO / rel).read_text(encoding="utf-8"))


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _public_files() -> list[pathlib.Path]:
    files = [REPO / "README.md"]
    files += [p for p in DOCS.rglob("*") if p.suffix in {".md", ".mdx"}]
    files += [REPO / "site" / "src" / "pages" / "index.astro"]
    return [p for p in files if p.exists()]


# --- gates: claims must map to ARCHITECTURE_INVARIANTS.json ------------------------

def test_gate_counts_come_from_the_invariants_file():
    inv, facts = _json("ARCHITECTURE_INVARIANTS.json"), _json("data/public-product-facts.json")
    assert facts["gates"] == inv["counts"]["gates"] == len(inv["gates"])
    br = inv["gate_breakdown"]
    assert facts["gates_active"] == br["evaluated_by_a_mode"]
    assert (facts["gates_hard_block"], facts["gates_block_ask"], facts["gates_warn"]) == (
        br["hard_block"], br["block_ask"], br["warn"])
    assert br["hard_block"] + br["block_ask"] + br["warn"] == facts["gates"]


def test_gates_are_never_called_approval_gates():
    rx = re.compile(r"\bapproval[- ]gates?\b", re.I)
    bad = [str(p.relative_to(REPO)) for p in _public_files() if rx.search(_text(p))]
    assert not bad, f"'approval gates' is retired, say 'gate checks': {bad}"


def test_hard_block_means_no_write_not_no_analysis():
    text = _text(DOCS / "approval-model.md")
    assert "gate check" in text.lower()
    assert "hard block" in text.lower()


# --- families, workflows, integrations ---------------------------------------------

def test_no_workflow_or_verification_family():
    cat = _json("data/public-capabilities.json")
    names = json.dumps(cat["families"]).lower()
    assert "new project architecture" not in names
    assert "verification" not in names
    assert len(cat["families"]) == _json("data/public-product-facts.json")["capability_families"]


def test_homepage_numbers_come_from_facts_not_literals():
    page = _text(REPO / "site" / "src" / "pages" / "index.astro")
    for key in ("gates", "gates_active", "architecture_score", "tests"):
        assert f"facts.{key}" in page, f"index.astro must render facts.{key}, not a literal"
    assert not re.search(r"\b\d{1,2}\s+gates\b", page)


# --- Completion Guardian: optional, external, never counted --------------------------

def test_guardian_is_not_a_capability():
    cat = _json("data/public-capabilities.json")
    for cap in cat["capabilities"]:
        blob = " ".join(str(cap.get(k, "")) for k in ("id", "name", "summary", "command")).lower()
        assert "guardian" not in blob, f"{cap['id']}: Guardian is an integration, not a capability"
    assert "guardian" not in json.dumps(cat["families"]).lower()


def test_guardian_page_states_optional_external_and_not_proof():
    text = _text(DOCS / "completion-guardian.md").lower()
    for needle in ("optional", "separate install", "not a capability", "not a proof", "fingerprint"):
        assert needle in text, f"completion-guardian.md must say: {needle}"


def test_guardian_is_in_the_integrations_group_only():
    cfg = _text(REPO / "site" / "astro.config.mjs")
    m = re.search(r"label: 'Integrations', items: \[([^\]]*)\]", cfg)
    assert m and "completion-guardian" in m.group(1)
    assert "completion-guardian" not in cfg.replace(m.group(0), "")


# --- CLI / skill / MCP distinctions ---------------------------------------------------

def test_cli_init_is_github_plus_llm_and_skill_is_broader():
    text = _text(DOCS / "new-projects.md").lower()
    assert "github" in text and "llm_api_key" in text
    assert "skill" in text
    lim = _text(DOCS / "limitations.md").lower()
    assert "github only" in lim or "searches github" in lim


def test_mcp_is_four_read_only_tools_with_no_network():
    from genesis_architect.pro import mcp_tools

    facts = _json("data/public-product-facts.json")
    assert facts["mcp_tools"] == len(mcp_tools.TOOLS) == 4
    text = _text(DOCS / "mcp.md").lower()
    assert "read-only" in text
    assert "network" in text


def test_source_registry_is_classification_not_per_run_querying():
    facts = _json("data/public-product-facts.json")
    assert (facts["research_sources"], facts["research_tiers"]) == (
        _json("ARCHITECTURE_INVARIANTS.json")["counts"]["research_sources"],
        _json("ARCHITECTURE_INVARIANTS.json")["counts"]["research_tiers"],
    )


# --- no old Pro confusion ----------------------------------------------------------------

def test_public_surface_does_not_present_pro_as_a_product():
    rx = re.compile(r"\bgenesis[- ]architect[- ]pro\b|\bGenesis Pro\b", re.I)
    allowed = {"limitations.md", "contributing.md", "security.md"}
    bad = []
    for p in _public_files():
        if p.name in allowed:
            continue
        for n, line in enumerate(_text(p).splitlines(), 1):
            if rx.search(line) and "genesis-architect-pro/" not in line and not re.search(r"discontinu|retired|deprecated|not a separate|no separate|unpublished|pip uninstall|no paid tier", line, re.I):
                bad.append(f"{p.relative_to(REPO)}:{n}")
    assert not bad, f"Pro appears as a current product: {bad}"
