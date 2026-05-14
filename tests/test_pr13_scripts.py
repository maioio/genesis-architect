"""Tests for pitfall_coverage_check.py and genesis_subcommands.py (PR#13 changes)."""
import json
import os
import sys
import textwrap
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


# ---------------------------------------------------------------------------
# pitfall_coverage_check
# ---------------------------------------------------------------------------

# parse_pitfalls splits on '## Pitfall N' headers via regex that stops at '#'.
# In real PITFALLS.md files, GitHub issue URLs like [repo#123](url#fragment) contain
# '#' which causes the regex to split mid-header, leaving the mitigation text in the
# next section (body). Tests must mirror this real-world format.
PITFALLS_REAL_FORMAT = textwrap.dedent("""\
    ## Pitfall 1: Dependency hell
    **Seen in**: [some/repo#1](https://github.com/some/repo/issues/1)
    **Root cause**: pinning is hard.
    **Our mitigation**: pin all versions strictly in requirements.txt

    ## Pitfall 2: Another issue
    **Seen in**: [some/repo#2](https://github.com/some/repo/issues/2)
    **Our mitigation**: use retry with backoff on transient failures
    """)


class TestParsePitfalls:
    def test_parses_pitfall_with_mitigation(self, tmp_path):
        from pitfall_coverage_check import parse_pitfalls
        p = tmp_path / "PITFALLS.md"
        p.write_text(PITFALLS_REAL_FORMAT, encoding="utf-8")
        result = parse_pitfalls(p)
        assert "pitfall_1" in result
        assert "pin" in result["pitfall_1"]

    def test_parses_multiple_pitfalls(self, tmp_path):
        from pitfall_coverage_check import parse_pitfalls
        p = tmp_path / "PITFALLS.md"
        p.write_text(PITFALLS_REAL_FORMAT, encoding="utf-8")
        result = parse_pitfalls(p)
        assert len(result) == 2
        assert "pitfall_1" in result
        assert "pitfall_2" in result

    def test_returns_empty_on_no_pitfalls(self, tmp_path):
        from pitfall_coverage_check import parse_pitfalls
        p = tmp_path / "PITFALLS.md"
        p.write_text("# Just a header\nNo pitfall sections here.\n", encoding="utf-8")
        result = parse_pitfalls(p)
        assert result == {}


class TestExtractKeywords:
    def test_skips_stop_words(self):
        from pitfall_coverage_check import extract_keywords
        kws = extract_keywords("use the virtualenv for isolation")
        assert "the" not in kws
        assert "use" not in kws
        assert "for" not in kws

    def test_returns_up_to_three(self):
        from pitfall_coverage_check import extract_keywords
        kws = extract_keywords("pin lock retry cache warmup deploy rollback")
        assert len(kws) <= 3

    def test_deduplicates(self):
        from pitfall_coverage_check import extract_keywords
        kws = extract_keywords("retry retry retry")
        assert kws.count("retry") == 1

    def test_skips_short_words(self):
        from pitfall_coverage_check import extract_keywords
        kws = extract_keywords("do it go run big cache")
        assert all(len(w) > 2 for w in kws)


class TestCollectSourceFiles:
    def test_collects_known_extensions(self, tmp_path):
        from pitfall_coverage_check import collect_source_files
        (tmp_path / "main.py").write_text("pass")
        (tmp_path / "app.ts").write_text("export {}")
        (tmp_path / "README.md").write_text("docs")
        files = collect_source_files(tmp_path)
        names = [f.name for f in files]
        assert "main.py" in names
        assert "app.ts" in names
        assert "README.md" not in names

    def test_ignores_non_code_files(self, tmp_path):
        from pitfall_coverage_check import collect_source_files
        (tmp_path / "data.csv").write_text("a,b,c")
        (tmp_path / "Makefile").write_text("all:")
        files = collect_source_files(tmp_path)
        assert files == []


class TestSearchKeyword:
    def test_finds_keyword_in_file(self, tmp_path):
        from pitfall_coverage_check import search_keyword_in_files
        f = tmp_path / "main.py"
        f.write_text("import virtualenv\nprint('hello')\n")
        matches = search_keyword_in_files("virtualenv", [f])
        assert len(matches) == 1
        assert "main.py" in matches[0]

    def test_case_insensitive(self, tmp_path):
        from pitfall_coverage_check import search_keyword_in_files
        f = tmp_path / "app.py"
        f.write_text("# Use VirtualEnv for isolation\n")
        matches = search_keyword_in_files("virtualenv", [f])
        assert len(matches) == 1

    def test_returns_empty_when_not_found(self, tmp_path):
        from pitfall_coverage_check import search_keyword_in_files
        f = tmp_path / "app.py"
        f.write_text("print('nothing here')\n")
        matches = search_keyword_in_files("xyznotpresent", [f])
        assert matches == []

    def test_one_match_per_file(self, tmp_path):
        from pitfall_coverage_check import search_keyword_in_files
        f = tmp_path / "main.py"
        f.write_text("retry = True\nretry_count = 3\n")
        matches = search_keyword_in_files("retry", [f])
        assert len(matches) == 1

    def test_skips_unreadable_file(self, tmp_path):
        from pitfall_coverage_check import search_keyword_in_files
        f = tmp_path / "bad.py"
        f.write_text("content")
        # Simulate OSError by patching Path.read_text
        with mock.patch("pathlib.Path.read_text", side_effect=OSError("perm denied")):
            matches = search_keyword_in_files("content", [f])
        assert matches == []


class TestDeduplicate:
    def test_removes_duplicates(self):
        from pitfall_coverage_check import _deduplicate
        result = _deduplicate(["a", "b", "a", "c", "b"])
        assert result == ["a", "b", "c"]

    def test_empty_list(self):
        from pitfall_coverage_check import _deduplicate
        assert _deduplicate([]) == []


class TestCheckPitfall:
    def test_found_when_keyword_present(self, tmp_path):
        from pitfall_coverage_check import _check_pitfall
        f = tmp_path / "main.py"
        f.write_text("virtualenv.create('env')\n")
        result = _check_pitfall("pitfall_1", "use virtualenv isolation", [f])
        assert result["found"] is True

    def test_not_found_when_keyword_absent(self, tmp_path):
        from pitfall_coverage_check import _check_pitfall
        f = tmp_path / "main.py"
        f.write_text("print('nothing relevant')\n")
        result = _check_pitfall("pitfall_1", "use virtualenv isolation", [f])
        assert result["found"] is False

    def test_result_has_required_keys(self, tmp_path):
        from pitfall_coverage_check import _check_pitfall
        result = _check_pitfall("pitfall_1", "retry logic timeout", [])
        assert "mitigation" in result
        assert "found" in result
        assert "matches" in result


class TestPrintSummary:
    def test_returns_missing_ids(self, capsys):
        from pitfall_coverage_check import _print_summary
        results = {
            "pitfall_1": {"found": True, "mitigation": "virtualenv", "matches": ["f:1"]},
            "pitfall_2": {"found": False, "mitigation": "retry", "matches": []},
        }
        missing = _print_summary(results)
        assert missing == ["pitfall_2"]

    def test_returns_empty_when_all_found(self, capsys):
        from pitfall_coverage_check import _print_summary
        results = {
            "pitfall_1": {"found": True, "mitigation": "virtualenv", "matches": ["f:1"]},
        }
        missing = _print_summary(results)
        assert missing == []


# ---------------------------------------------------------------------------
# genesis_subcommands
# ---------------------------------------------------------------------------

class TestDetectEcosystem:
    def test_detects_pypi_from_requirements(self, tmp_path):
        from genesis_subcommands import detect_ecosystem
        (tmp_path / "requirements.txt").write_text("requests==2.28.0\n")
        assert detect_ecosystem(str(tmp_path)) == "PyPI"

    def test_detects_pypi_from_pyproject(self, tmp_path):
        from genesis_subcommands import detect_ecosystem
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n")
        assert detect_ecosystem(str(tmp_path)) == "PyPI"

    def test_detects_npm(self, tmp_path):
        from genesis_subcommands import detect_ecosystem
        (tmp_path / "package.json").write_text("{}")
        assert detect_ecosystem(str(tmp_path)) == "npm"

    def test_detects_go(self, tmp_path):
        from genesis_subcommands import detect_ecosystem
        (tmp_path / "go.mod").write_text("module example.com/app\n")
        assert detect_ecosystem(str(tmp_path)) == "Go"

    def test_detects_rust(self, tmp_path):
        from genesis_subcommands import detect_ecosystem
        (tmp_path / "Cargo.toml").write_text("[package]\n")
        assert detect_ecosystem(str(tmp_path)) == "crates.io"

    def test_defaults_to_pypi(self, tmp_path):
        from genesis_subcommands import detect_ecosystem
        assert detect_ecosystem(str(tmp_path)) == "PyPI"


class TestExtractDepsFromResearch:
    def test_extracts_pinned_versions(self, tmp_path):
        from genesis_subcommands import extract_deps_from_research
        md = tmp_path / "RESEARCH.md"
        md.write_text("Use requests==2.28.0 and pytest>=7.0.0 in tests.\n")
        deps = extract_deps_from_research(str(md))
        assert "requests" in deps
        assert deps["requests"] == "2.28.0"

    def test_returns_empty_when_file_missing(self, tmp_path):
        from genesis_subcommands import extract_deps_from_research
        deps = extract_deps_from_research(str(tmp_path / "RESEARCH.md"))
        assert deps == {}

    def test_returns_empty_when_no_pins(self, tmp_path):
        from genesis_subcommands import extract_deps_from_research
        md = tmp_path / "RESEARCH.md"
        md.write_text("Use requests and pytest for testing.\n")
        deps = extract_deps_from_research(str(md))
        assert deps == {}


class TestExtractFixVersion:
    def test_extracts_fix_from_vuln(self):
        from genesis_subcommands import extract_fix_version
        vuln = {"affected": [{"ranges": [{"events": [{"introduced": "0"}, {"fixed": "2.29.0"}]}]}]}
        assert extract_fix_version(vuln) == "2.29.0"

    def test_returns_none_when_no_fix(self):
        from genesis_subcommands import extract_fix_version
        assert extract_fix_version({}) is None

    def test_returns_none_when_only_introduced(self):
        from genesis_subcommands import extract_fix_version
        vuln = {"affected": [{"ranges": [{"events": [{"introduced": "0"}]}]}]}
        assert extract_fix_version(vuln) is None


class TestCheckActions:
    def test_detects_outdated_action(self, tmp_path):
        from genesis_subcommands import check_actions
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("uses: actions/checkout@v4\n")
        warnings = check_actions(str(tmp_path))
        assert any(w["action"] == "actions/checkout" for w in warnings)

    def test_no_warning_for_current_version(self, tmp_path):
        from genesis_subcommands import check_actions
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("uses: actions/checkout@v6\n")
        warnings = check_actions(str(tmp_path))
        assert not any(w["action"] == "actions/checkout" for w in warnings)

    def test_no_warnings_for_unknown_action(self, tmp_path):
        from genesis_subcommands import check_actions
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("uses: myorg/custom-action@v1\n")
        warnings = check_actions(str(tmp_path))
        assert warnings == []

    def test_empty_when_no_workflows(self, tmp_path):
        from genesis_subcommands import check_actions
        warnings = check_actions(str(tmp_path))
        assert warnings == []


class TestQueryOsv:
    def test_returns_empty_on_network_error(self):
        from genesis_subcommands import query_osv
        import urllib.error
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            result = query_osv("requests", "PyPI")
        assert result == []

    def test_returns_vulns_on_success(self):
        from genesis_subcommands import query_osv
        fake_response = json.dumps({"vulns": [{"id": "GHSA-001"}]}).encode()
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = fake_response
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=mock_resp):
            result = query_osv("requests", "PyPI")
        assert len(result) == 1
        assert result[0]["id"] == "GHSA-001"

    def test_returns_empty_when_no_vulns_key(self):
        from genesis_subcommands import query_osv
        fake_response = json.dumps({}).encode()
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = fake_response
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=mock_resp):
            result = query_osv("requests", "PyPI")
        assert result == []


class TestCmdCheck:
    def test_returns_zero_when_no_issues(self, tmp_path, capsys):
        from genesis_subcommands import cmd_check
        with mock.patch("genesis_subcommands.query_osv", return_value=[]):
            code = cmd_check(str(tmp_path))
        assert code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["critical"] == []

    def test_returns_one_when_cve_found(self, tmp_path, capsys):
        from genesis_subcommands import cmd_check
        md = tmp_path / "RESEARCH.md"
        md.write_text("requests==2.0.0\n")
        fake_vuln = {
            "id": "GHSA-1234",
            "aliases": ["CVE-2023-1234"],
            "affected": [{"ranges": [{"events": [{"fixed": "2.29.0"}]}]}],
        }
        with mock.patch("genesis_subcommands.query_osv", return_value=[fake_vuln]):
            code = cmd_check(str(tmp_path))
        assert code == 1

    def test_output_is_valid_json(self, tmp_path, capsys):
        from genesis_subcommands import cmd_check
        with mock.patch("genesis_subcommands.query_osv", return_value=[]):
            cmd_check(str(tmp_path))
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "critical" in data
        assert "warnings" in data
        assert "info" in data

    def test_cve_without_cve_alias_uses_id(self, tmp_path, capsys):
        from genesis_subcommands import cmd_check
        md = tmp_path / "RESEARCH.md"
        md.write_text("requests==2.0.0\n")
        fake_vuln = {"id": "GHSA-9999", "aliases": [], "affected": []}
        with mock.patch("genesis_subcommands.query_osv", return_value=[fake_vuln]):
            code = cmd_check(str(tmp_path))
        assert code == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["critical"][0]["cve"] == "GHSA-9999"
