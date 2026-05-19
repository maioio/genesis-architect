"""Tests for issue_miner, feedback, and drift_detector."""
import sys
import json
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


class TestFeedback:
    def test_record_and_retrieve(self, tmp_path):
        from feedback import record, _load
        record("path traversal", "python", "helpful", project_root=tmp_path)
        entries = _load(project_root=tmp_path)
        assert len(entries) == 1
        assert entries[0]["rating"] == "helpful"
        assert entries[0]["topic"] == "path traversal"

    def test_invalid_rating_raises(self, tmp_path):
        from feedback import record
        with pytest.raises(ValueError):
            record("topic", "python", "unknown", project_root=tmp_path)

    def test_stats_aggregation(self, tmp_path):
        from feedback import record, stats
        record("csv", "python", "helpful", project_root=tmp_path)
        record("csv", "python", "helpful", project_root=tmp_path)
        record("auth", "python", "irrelevant", project_root=tmp_path)
        s = stats(project_root=tmp_path)
        assert s["total"] == 3
        assert s["by_rating"]["helpful"] == 2
        assert s["by_rating"]["irrelevant"] == 1


class TestDriftDetector:
    def test_no_drift_on_clean_project(self, tmp_path):
        from drift_detector import detect_drift
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()
        report = detect_drift(str(tmp_path))
        assert report.missing_dirs == []

    def test_detects_missing_dirs(self, tmp_path):
        from drift_detector import detect_drift
        # Only src exists, tests and docs are missing
        (tmp_path / "src").mkdir()
        report = detect_drift(str(tmp_path))
        assert "tests" in report.missing_dirs or "docs" in report.missing_dirs

    def test_adr_not_found_flag(self, tmp_path):
        from drift_detector import detect_drift
        report = detect_drift(str(tmp_path))
        assert report.adr_found is False

    def test_level1_only_skips_import_check(self, tmp_path):
        from drift_detector import detect_drift
        # Write evidence.json with a forbidden import
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "evidence.json").write_text(
            '{"arch_rationale": "no database, file-based state", "archetype": "cli"}',
            encoding="utf-8",
        )
        src = tmp_path / "src"
        src.mkdir()
        (src / "bad.py").write_text("import sqlite3\n\ndef run(): pass\n")
        report = detect_drift(str(tmp_path), level=1)
        # Level 1 should NOT check imports
        assert report.import_violations == []

    def test_level2_detects_forbidden_import(self, tmp_path):
        from drift_detector import detect_drift
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "evidence.json").write_text(
            '{"arch_rationale": "no database, file-based state", "archetype": "cli"}',
            encoding="utf-8",
        )
        src = tmp_path / "src"
        src.mkdir()
        (src / "bad.py").write_text("import sqlite3\n\ndef run(): pass\n")
        report = detect_drift(str(tmp_path), level=2)
        assert report.has_import_violations
        modules = [v.module for v in report.import_violations]
        assert "sqlite3" in modules

    def test_level2_no_violation_when_no_forbidden(self, tmp_path):
        from drift_detector import detect_drift
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        # CLI archetype - flask is forbidden
        (genesis / "evidence.json").write_text(
            '{"arch_rationale": "no server", "archetype": "cli"}',
            encoding="utf-8",
        )
        src = tmp_path / "src"
        src.mkdir()
        # Uses requests, not flask - should be clean
        (src / "fetcher.py").write_text("import requests\ndef fetch(url): return requests.get(url)\n")
        report = detect_drift(str(tmp_path), level=2)
        assert not report.has_import_violations

    def test_level2_cli_archetype_forbids_flask(self, tmp_path):
        from drift_detector import detect_drift
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "evidence.json").write_text(
            '{"arch_rationale": "pure cli tool", "archetype": "cli"}',
            encoding="utf-8",
        )
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("import flask\napp = flask.Flask(__name__)\n")
        report = detect_drift(str(tmp_path), level=2)
        assert report.has_import_violations
        assert any(v.module == "flask" for v in report.import_violations)

    def test_report_ok_property(self, tmp_path):
        from drift_detector import detect_drift
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()
        report = detect_drift(str(tmp_path), level=2)
        # No evidence.json and standard dirs present -> ok
        assert report.ok

    def test_violation_contains_file_and_line(self, tmp_path):
        from drift_detector import detect_drift
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "evidence.json").write_text(
            '{"arch_rationale": "no database", "archetype": "cli"}',
            encoding="utf-8",
        )
        src = tmp_path / "src"
        src.mkdir()
        (src / "dal.py").write_text("import sqlite3\n\ndef query(): pass\n")
        report = detect_drift(str(tmp_path), level=2)
        assert len(report.import_violations) == 1
        v = report.import_violations[0]
        assert v.file.endswith("dal.py")
        assert v.line == 1
        assert v.module == "sqlite3"
        assert v.rule == "forbidden"

    def test_json_output_shape(self, tmp_path):
        from drift_detector import DriftReport, print_json_report
        import io, json
        report = DriftReport()
        report.new_dirs = ["tmp"]
        report.missing_dirs = []
        report.adr_found = False
        report.evidence_found = False
        buf = io.StringIO()
        import sys
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            print_json_report(report)
        finally:
            sys.stdout = old_stdout
        data = json.loads(buf.getvalue())
        assert "ok" in data
        assert "structural_drift" in data
        assert "import_violations" in data
        assert data["structural_drift"]["new_dirs"] == ["tmp"]


class TestIssueMinerClassify:
    def test_classify_security(self):
        from issue_miner import _classify
        assert _classify("SQL injection vulnerability in query builder", []) == "security"

    def test_classify_performance(self):
        from issue_miner import _classify
        assert _classify("Memory leak when processing large files", []) == "performance"

    def test_classify_breaking(self):
        from issue_miner import _classify
        assert _classify("Breaking change in version 3.0 API", []) == "breaking"

    def test_classify_bug_default(self):
        from issue_miner import _classify
        assert _classify("Button click not working in Firefox", []) == "bug"

    def test_classify_by_label(self):
        from issue_miner import _classify
        assert _classify("Some issue title", ["security"]) == "security"
