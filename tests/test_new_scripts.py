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
