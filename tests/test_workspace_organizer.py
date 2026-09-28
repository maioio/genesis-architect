"""Tests for workspace_organizer.py — the Organize engine.

This module moves files, so most of what follows tests what it REFUSES to
move. Every safety rule in the module docstring gets at least one test that
would fail loudly if the rule were removed.
"""

from __future__ import annotations

from genesis_architect_pro.workspace_organizer import (
    DEFAULT_SAFE_PATHS,
    OrganizeReport,
    format_report,
    init_rules,
    load_rules,
    organize,
    rules_path_for,
)


# ---------------------------------------------------------------------------
# Dry-run default
# ---------------------------------------------------------------------------


class TestDryRunByDefault:
    def test_dry_run_reports_but_does_not_move(self, tmp_path):
        (tmp_path / "debug.log").write_text("x")
        report = organize(tmp_path)
        assert report.dry_run is True
        assert (tmp_path / "debug.log").exists()
        assert not (tmp_path / "logs" / "debug.log").exists()
        assert len(report.candidates) == 1

    def test_apply_actually_moves(self, tmp_path):
        (tmp_path / "debug.log").write_text("x")
        report = organize(tmp_path, apply=True)
        assert report.dry_run is False
        assert not (tmp_path / "debug.log").exists()
        assert (tmp_path / "logs" / "debug.log").exists()
        assert report.moved == [str(tmp_path / "debug.log")]

    def test_dry_run_is_the_default_argument(self, tmp_path):
        (tmp_path / "x.tmp").write_text("x")
        report = organize(tmp_path)  # apply not passed
        assert report.dry_run is True
        assert (tmp_path / "x.tmp").exists()


# ---------------------------------------------------------------------------
# Safe paths are never touched
# ---------------------------------------------------------------------------


class TestSafePaths:
    def test_default_safe_path_is_protected(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("x")
        report = organize(tmp_path)
        assert not report.candidates
        assert any(p.path.name == "CLAUDE.md" for p in report.protected)

    def test_rules_file_cannot_narrow_the_safe_path_floor(self, tmp_path):
        # Even if a rules file tries to route README.md somewhere, the
        # built-in safe-path floor still wins — safe_paths only ever widens.
        genesis_dir = tmp_path / ".genesis"
        genesis_dir.mkdir()
        (genesis_dir / "organize_rules.yaml").write_text(
            "safe_paths: []\n"
            "rules:\n"
            "  - match: 'README.md'\n"
            "    target: 'docs/'\n"
        )
        (tmp_path / "README.md").write_text("x")
        report = organize(tmp_path)
        assert not report.candidates
        assert any(p.path.name == "README.md" for p in report.protected)

    def test_custom_safe_path_from_rules_file_is_honored(self, tmp_path):
        genesis_dir = tmp_path / ".genesis"
        genesis_dir.mkdir()
        (genesis_dir / "organize_rules.yaml").write_text(
            "safe_paths:\n  - keep_me.log\n"
            "rules:\n  - match: '*.log'\n    target: 'logs/'\n"
        )
        (tmp_path / "keep_me.log").write_text("x")
        report = organize(tmp_path)
        assert not report.candidates
        assert any(p.path.name == "keep_me.log" for p in report.protected)


# ---------------------------------------------------------------------------
# Files only, top level only
# ---------------------------------------------------------------------------


class TestFilesOnlyTopLevelOnly:
    def test_directories_are_never_moved(self, tmp_path):
        (tmp_path / "logs").mkdir()  # named exactly like a rule target
        report = organize(tmp_path)
        assert not report.candidates

    def test_nested_files_are_not_descended_into(self, tmp_path):
        nested = tmp_path / "some_dir"
        nested.mkdir()
        (nested / "debug.log").write_text("x")
        report = organize(tmp_path)
        assert not report.candidates
        assert not report.protected


# ---------------------------------------------------------------------------
# Project-scoped
# ---------------------------------------------------------------------------


class TestProjectScoped:
    def test_rule_target_escaping_root_is_protected_not_moved(self, tmp_path):
        genesis_dir = tmp_path / ".genesis"
        genesis_dir.mkdir()
        (genesis_dir / "organize_rules.yaml").write_text(
            "rules:\n  - match: '*.log'\n    target: '../escape/'\n"
        )
        (tmp_path / "debug.log").write_text("x")
        report = organize(tmp_path)
        assert not report.candidates
        assert any("escapes project root" in p.reason for p in report.protected)
        assert not (tmp_path.parent / "escape").exists()


# ---------------------------------------------------------------------------
# No rule matched is not silence
# ---------------------------------------------------------------------------


class TestUnmatchedFilesAreRecorded:
    def test_unmatched_file_is_protected_with_reason(self, tmp_path):
        (tmp_path / "notes.txt").write_text("x")
        report = organize(tmp_path)
        assert not report.candidates
        match = next(p for p in report.protected if p.path.name == "notes.txt")
        assert "no rule matched" in match.reason


# ---------------------------------------------------------------------------
# Fail safe on a malformed rules file
# ---------------------------------------------------------------------------


class TestMalformedRulesFileFailsSafe:
    def test_malformed_yaml_falls_back_to_defaults(self, tmp_path):
        genesis_dir = tmp_path / ".genesis"
        genesis_dir.mkdir()
        (genesis_dir / "organize_rules.yaml").write_text("not: valid: yaml: [[[")
        (tmp_path / "debug.log").write_text("x")

        safe_paths, rules, errors = load_rules(tmp_path)
        assert errors  # the failure is recorded, not swallowed silently
        assert safe_paths == DEFAULT_SAFE_PATHS
        assert rules  # still usable — falls back rather than returning nothing

    def test_non_mapping_top_level_falls_back(self, tmp_path):
        genesis_dir = tmp_path / ".genesis"
        genesis_dir.mkdir()
        (genesis_dir / "organize_rules.yaml").write_text("- just\n- a\n- list\n")
        safe_paths, rules, errors = load_rules(tmp_path)
        assert errors
        assert safe_paths == DEFAULT_SAFE_PATHS

    def test_malformed_rule_entry_is_skipped_not_fatal(self, tmp_path):
        genesis_dir = tmp_path / ".genesis"
        genesis_dir.mkdir()
        (genesis_dir / "organize_rules.yaml").write_text(
            "rules:\n"
            "  - match: '*.log'\n"
            "    target: 'logs/'\n"
            "  - just_a_string\n"
        )
        safe_paths, rules, errors = load_rules(tmp_path)
        assert any("malformed rule entry" in e for e in errors)
        assert {"match": "*.log", "target": "logs/"} in rules

    def test_missing_rules_file_uses_defaults_with_no_error(self, tmp_path):
        safe_paths, rules, errors = load_rules(tmp_path)
        assert errors == []
        assert safe_paths == DEFAULT_SAFE_PATHS


# ---------------------------------------------------------------------------
# init_rules bootstrap
# ---------------------------------------------------------------------------


class TestInitRules:
    def test_writes_default_file_when_absent(self, tmp_path):
        path, created = init_rules(tmp_path)
        assert created is True
        assert path == rules_path_for(tmp_path)
        assert path.is_file()
        assert "safe_paths" in path.read_text(encoding="utf-8")

    def test_never_overwrites_an_existing_file(self, tmp_path):
        genesis_dir = tmp_path / ".genesis"
        genesis_dir.mkdir()
        custom = genesis_dir / "organize_rules.yaml"
        custom.write_text("# my own rules\nrules: []\n")
        path, created = init_rules(tmp_path)
        assert created is False
        assert path.read_text(encoding="utf-8") == "# my own rules\nrules: []\n"

    def test_init_rules_itself_never_moves_anything(self, tmp_path):
        (tmp_path / "debug.log").write_text("x")
        init_rules(tmp_path)
        assert (tmp_path / "debug.log").exists()


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


class TestReporting:
    def test_summary_dry_run_clean(self):
        assert "clean" in OrganizeReport(dry_run=True).summary().lower() or \
            "tidy" in OrganizeReport(dry_run=True).summary().lower()

    def test_format_report_includes_move_marker_on_dry_run(self, tmp_path):
        (tmp_path / "debug.log").write_text("x")
        report = organize(tmp_path)
        text = format_report(report)
        assert "Would move" in text
        assert "Nothing was moved" in text

    def test_format_report_includes_moved_section_on_apply(self, tmp_path):
        (tmp_path / "debug.log").write_text("x")
        report = organize(tmp_path, apply=True)
        text = format_report(report)
        assert "Moved" in text
