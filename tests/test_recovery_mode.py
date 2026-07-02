"""Tests for V5.4 genesis recover command in SKILL.md and recovery_scan.py."""

from __future__ import annotations

import json
from pathlib import Path

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
