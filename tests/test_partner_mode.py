"""Tests for V5.1 Development Partner Mode rules in SKILL.md."""

import re
from pathlib import Path

SKILL_MD = Path(__file__).parent.parent / "SKILL.md"


def _skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


# --- Experience Selection ---

def test_experience_selection_has_four_options():
    text = _skill_text()
    section_start = text.find("## Phase 0.5")
    section_end = text.find("## Phase 1")
    section = text[section_start:section_end]
    assert "A:" in section
    assert "B:" in section
    assert "C:" in section
    assert "D:" in section


def test_experience_selection_has_recommended_marker():
    text = _skill_text()
    section_start = text.find("## Phase 0.5")
    section_end = text.find("## Phase 1")
    section = text[section_start:section_end]
    assert "Recommended" in section, "One option must be marked as Recommended"


def test_experience_selection_fast_maps_to_fast_mvp():
    text = _skill_text()
    section_start = text.find("## Phase 0.5")
    section_end = text.find("## Phase 1")
    section = text[section_start:section_end]
    # Fast Build mode must connect to --fast-mvp behavior
    assert "--fast-mvp" in section or "fast-mvp" in section.lower()


def test_experience_selection_skips_for_explicit_commands():
    text = _skill_text()
    section_start = text.find("## Phase 0.5")
    section_end = text.find("## Phase 1")
    section = text[section_start:section_end]
    # Must skip for explicit genesis commands
    assert "genesis audit" in section
    assert "genesis init" in section


# --- Development Partner Rules ---

def test_partner_rules_present_in_skill():
    text = _skill_text()
    assert "Development Partner Rules" in text


def test_partner_rules_define_major_decisions():
    text = _skill_text()
    # The 5 major decision categories must be explicit
    assert "Architecture" in text
    assert "MVP scope" in text
    assert "Technology" in text
    assert "Product direction" in text
    assert "Business" in text


def test_partner_rules_define_excluded_decisions():
    text = _skill_text()
    # Must explicitly list what Genesis does NOT ask before
    assert "does NOT ask before" in text or "does not ask before" in text.lower()
    assert "file names" in text or "file name" in text


def test_question_format_has_abcd_structure():
    text = _skill_text()
    section_start = text.find("Question format")
    assert section_start != -1, "Question format section must exist"
    section = text[section_start:section_start + 300]
    assert "A:" in section
    assert "B:" in section
    assert "C:" in section
    assert "D:" in section


def test_question_format_has_why_field():
    text = _skill_text()
    section_start = text.find("Question format")
    section = text[section_start:section_start + 300]
    assert "Why" in section, "Question format must include a Why field for the recommendation"


def test_question_format_has_risk_field():
    text = _skill_text()
    section_start = text.find("Question format")
    section = text[section_start:section_start + 300]
    assert "Risk" in section or "risk" in section, "Question format must include risk of choosing differently"


def test_question_format_has_default_accept():
    text = _skill_text()
    # User must be able to accept the default without typing anything
    assert "Enter" in text and "accept" in text, "Must support pressing Enter to accept recommended default"


def test_partner_rules_active_in_companion_mode():
    """Development Partner rules must persist beyond Phase 6 into companion mode."""
    text = _skill_text()
    phase7_start = text.find("## Phase 7")
    phase7_section = text[phase7_start:phase7_start + 500]
    assert "Development Partner" in phase7_section or "Partner Rules" in phase7_section, (
        "Phase 7 must reference Development Partner rules remaining active"
    )


# --- SKILL.md constraints ---

def test_skill_md_under_400_lines():
    lines = SKILL_MD.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 400, f"SKILL.md is {len(lines)} lines, limit is 400"


def test_skill_md_no_em_dashes():
    text = SKILL_MD.read_text(encoding="utf-8")
    em_dash_lines = [
        i + 1 for i, line in enumerate(text.splitlines())
        if "—" in line or "–" in line
    ]
    assert not em_dash_lines, f"Em dashes found on lines: {em_dash_lines}"
