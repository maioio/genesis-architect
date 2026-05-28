"""Tests for platform_risks support added to pitfall_coverage_check.py in v2.4.0."""
import sys
import unittest.mock as mock
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent

from genesis_architect.core.pitfall_coverage_check import parse_platform_risks, check_platform_risks, main


PITFALLS_WITH_RISKS = """\
# PITFALLS.md

## Pitfall 1: Console encoding
**Where**: https://github.com/example/repo/issues/42
**Why**: Windows uses cp1252 by default.
**Mitigation**: Set PYTHONIOENCODING=utf-8 in entrypoint.
mitigation_file_path: src/myapp/utils/security.py

## Pitfall 2: Path separators
**Where**: https://github.com/example/repo/issues/99
**Why**: Backslash vs forward-slash.
**Mitigation**: Use pathlib.Path throughout.
mitigation_file_path: src/myapp/core.py

platform_risks:
  - name: Unicode encoding
    platform: windows
    mitigation_path: src/myapp/utils/security.py
  - name: Path separator
    platform: windows
    acknowledged: true
"""

PITFALLS_NO_RISKS = """\
# PITFALLS.md

## Pitfall 1: Example
**Where**: https://github.com/example/repo/issues/1
mitigation_file_path: src/myapp/core.py
"""

PITFALLS_INCOMPLETE_RISK = """\
# PITFALLS.md

platform_risks:
  - name: Filesystem chars
    platform: windows
"""


class TestParsePlatformRisks:
    def test_parses_risks_from_pitfalls(self, tmp_path):
        f = tmp_path / "PITFALLS.md"
        f.write_text(PITFALLS_WITH_RISKS, encoding="utf-8")
        risks = parse_platform_risks(f)
        assert len(risks) == 2

    def test_first_risk_has_name_and_platform(self, tmp_path):
        f = tmp_path / "PITFALLS.md"
        f.write_text(PITFALLS_WITH_RISKS, encoding="utf-8")
        risks = parse_platform_risks(f)
        assert risks[0]["name"] == "Unicode encoding"
        assert risks[0]["platform"] == "windows"

    def test_first_risk_has_mitigation_path(self, tmp_path):
        f = tmp_path / "PITFALLS.md"
        f.write_text(PITFALLS_WITH_RISKS, encoding="utf-8")
        risks = parse_platform_risks(f)
        assert "mitigation_path" in risks[0]

    def test_second_risk_is_acknowledged(self, tmp_path):
        f = tmp_path / "PITFALLS.md"
        f.write_text(PITFALLS_WITH_RISKS, encoding="utf-8")
        risks = parse_platform_risks(f)
        assert risks[1].get("acknowledged") == "true"

    def test_returns_empty_when_no_section(self, tmp_path):
        f = tmp_path / "PITFALLS.md"
        f.write_text(PITFALLS_NO_RISKS, encoding="utf-8")
        risks = parse_platform_risks(f)
        assert risks == []


class TestCheckPlatformRisks:
    def test_passes_when_mitigation_file_exists(self, tmp_path):
        # Create the mitigation file
        (tmp_path / "src" / "myapp" / "utils").mkdir(parents=True)
        (tmp_path / "src" / "myapp" / "utils" / "security.py").write_text("# ok")
        risks = [{"name": "Encoding", "platform": "windows",
                  "mitigation_path": "src/myapp/utils/security.py"}]
        errors = check_platform_risks(risks, tmp_path / "src")
        assert errors == []

    def test_passes_when_acknowledged_true(self, tmp_path):
        risks = [{"name": "Encoding", "platform": "windows", "acknowledged": "true"}]
        errors = check_platform_risks(risks, tmp_path / "src")
        assert errors == []

    def test_fails_when_no_mitigation_and_not_acknowledged(self, tmp_path):
        risks = [{"name": "Encoding", "platform": "windows"}]
        errors = check_platform_risks(risks, tmp_path / "src")
        assert len(errors) == 1
        assert "acknowledged" in errors[0] or "mitigation_path" in errors[0]

    def test_fails_when_mitigation_file_missing(self, tmp_path):
        risks = [{"name": "Encoding", "platform": "windows",
                  "mitigation_path": "src/nonexistent/security.py"}]
        errors = check_platform_risks(risks, tmp_path / "src")
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_returns_empty_for_empty_risks(self, tmp_path):
        errors = check_platform_risks([], tmp_path / "src")
        assert errors == []

    def test_handles_multiple_risks(self, tmp_path):
        (tmp_path / "src" / "myapp").mkdir(parents=True)
        (tmp_path / "src" / "myapp" / "security.py").write_text("# ok")
        risks = [
            {"name": "A", "platform": "windows", "acknowledged": "true"},
            {"name": "B", "platform": "windows",
             "mitigation_path": "src/myapp/security.py"},
        ]
        errors = check_platform_risks(risks, tmp_path / "src")
        assert errors == []


class TestMainFlagParsing:
    """Tests that invoke main() via sys.argv to cover --check-platform-risks flag parsing."""

    def test_main_exits_nonzero_when_platform_risk_has_no_mitigation(self, tmp_path):
        pitfalls = tmp_path / "PITFALLS.md"
        pitfalls.write_text(
            "## Pitfall 1: Encoding\n"
            "**Where**: https://github.com/example/repo/issues/1\n"
            "mitigation_file_path: src/myapp/core.py\n"
            "\nplatform_risks:\n"
            "  - name: Bad encoding\n"
            "    platform: windows\n",
            encoding="utf-8",
        )
        src = tmp_path / "src"
        src.mkdir()
        with mock.patch("sys.argv", [
            "pitfall_coverage_check.py",
            str(pitfalls),
            str(src),
            "--check-platform-risks",
        ]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code != 0

    def test_main_exits_zero_when_all_platform_risks_acknowledged(self, tmp_path):
        pitfalls = tmp_path / "PITFALLS.md"
        pitfalls.write_text(
            "## Pitfall 1: Encoding\n"
            "**Where**: https://github.com/example/repo/issues/1\n"
            "mitigation_file_path: src/myapp/core.py\n"
            "\nplatform_risks:\n"
            "  - name: Bad encoding\n"
            "    platform: windows\n"
            "    acknowledged: true\n",
            encoding="utf-8",
        )
        src = tmp_path / "src"
        src.mkdir()
        # main() does not raise SystemExit on success - it just returns
        with mock.patch("sys.argv", [
            "pitfall_coverage_check.py",
            str(pitfalls),
            str(src),
            "--check-platform-risks",
        ]):
            try:
                main()
            except SystemExit as e:
                assert e.code == 0, f"Expected exit 0, got {e.code}"
