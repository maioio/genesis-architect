"""Tests for V5.4 genesis recover command in SKILL.md and recovery_scan.py."""

from __future__ import annotations

import json
from pathlib import Path
import os as _os
import pytest as _pytest
def _public_root():
    env = _os.environ.get('GENESIS_CORE_ROOT')
    if env:
        return Path(env)
    return Path(__file__).parent.parent.parent / 'genesis-architect'


import pytest

SKILL_MD = _public_root() / "SKILL.md"


def _skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


# --- SKILL.md structural tests ---

def test_recover_command_in_skill():
    """genesis recover must appear in SKILL.md Invocation section."""
    text = _skill_text()
    inv_start = text.find("## Invocation")
    # find next section after Invocation
    next_section = text.find("\n## ", inv_start + 1)
    invocation = text[inv_start:next_section]
    assert "genesis recover" in invocation


def test_recover_is_readonly():
    """SKILL.md must state recover is read-only."""
    text = _skill_text()
    recover_start = text.find("`genesis recover")
    assert recover_start != -1
    section = text[recover_start:recover_start + 500]
    assert "read-only" in section or "no files modified" in section or "no code written" in section


def test_recover_produces_fragility_map():
    """SKILL.md must reference FRAGILITY_MAP.md as a recover output."""
    text = _skill_text()
    recover_start = text.find("`genesis recover")
    section = text[recover_start:recover_start + 600]
    assert "FRAGILITY_MAP.md" in section


def test_recover_produces_recovery_report():
    """SKILL.md must reference PROJECT_RECOVERY_REPORT.md as a recover output."""
    text = _skill_text()
    recover_start = text.find("`genesis recover")
    section = text[recover_start:recover_start + 600]
    assert "PROJECT_RECOVERY_REPORT.md" in section


def test_recover_skips_phase_05():
    """genesis recover must appear in Phase 0.5 skip conditions."""
    text = _skill_text()
    phase_05_start = text.find("## Phase 0.5")
    phase_05_end = text.find("\n## ", phase_05_start + 1)
    phase_05 = text[phase_05_start:phase_05_end]
    assert "genesis recover" in phase_05


def test_recover_module_granularity():
    """SKILL.md must specify module-level (not file-level) granularity for FRAGILITY_MAP."""
    text = _skill_text()
    recover_start = text.find("`genesis recover")
    section = text[recover_start:recover_start + 800]
    assert "module" in section.lower() or "component" in section.lower() or "responsibility" in section.lower()


def test_skill_md_under_400_lines():
    """400-line constraint must hold after V5.4 addition."""
    lines = SKILL_MD.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 400, f"SKILL.md is {len(lines)} lines, limit is 400"


def test_skill_md_no_em_dashes():
    text = SKILL_MD.read_text(encoding="utf-8")
    em_dash_lines = [i + 1 for i, line in enumerate(text.splitlines()) if "—" in line or "–" in line]
    assert not em_dash_lines, f"Em dashes found on lines: {em_dash_lines}"


# --- recovery_scan.py unit tests ---

def test_version_drift_detected(tmp_path: Path):
    """version_drift returns True when package.json and pyproject.toml have different versions."""
    from genesis_architect_pro.recovery_scan import version_drift

    (tmp_path / "package.json").write_text('{"name": "test", "version": "1.0.0"}')
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\nversion = "2.0.0"\n')
    result = version_drift(tmp_path)
    assert result["package.json"] == "1.0.0"
    assert result["pyproject.toml"] == "2.0.0"


def test_version_no_drift(tmp_path: Path):
    """version_drift returns consistent versions when they match."""
    from genesis_architect_pro.recovery_scan import version_drift

    (tmp_path / "package.json").write_text('{"name": "test", "version": "1.2.3"}')
    result = version_drift(tmp_path)
    assert result["package.json"] == "1.2.3"


def test_external_url_count_finds_urls(tmp_path: Path):
    """external_url_count counts hardcoded URLs in source files."""
    from genesis_architect_pro.recovery_scan import external_url_count

    src = tmp_path / "src"
    src.mkdir()
    (src / "api.js").write_text('const URL = "https://api.example.com/v1/data";\nconst B = "https://cdn.example.com/assets";')
    result = external_url_count(tmp_path)
    assert "src/api.js" in result or str(Path("src") / "api.js") in result
    counts = list(result.values())
    assert any(c >= 2 for c in counts)


def test_external_url_count_ignores_node_modules(tmp_path: Path):
    """external_url_count must skip node_modules."""
    from genesis_architect_pro.recovery_scan import external_url_count

    nm = tmp_path / "node_modules" / "lib"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text('const X = "https://should-not-count.com/api";')
    result = external_url_count(tmp_path)
    for key in result:
        assert "node_modules" not in key


def test_scan_returns_all_keys(tmp_path: Path):
    """scan() must return all required keys even on an empty project."""
    from genesis_architect_pro.recovery_scan import scan

    # Create minimal git repo so git commands don't error
    (tmp_path / ".git").mkdir()
    result = scan(tmp_path)
    assert "fix_commit_hotspots" in result
    assert "external_url_count" in result
    assert "version_sources" in result
    assert "version_drift" in result
    assert "dead_file_candidates" in result
    assert "doc_version" in result


def test_scan_json_serialisable(tmp_path: Path):
    """scan() output must be JSON-serialisable (used by genesis recover pipeline)."""
    from genesis_architect_pro.recovery_scan import scan

    (tmp_path / ".git").mkdir()
    result = scan(tmp_path)
    dumped = json.dumps(result)
    assert isinstance(dumped, str)
