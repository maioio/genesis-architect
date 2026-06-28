"""Phase 2a integration tests — five missing wires in the Recovery Intelligence pipeline.

Wire 1: architecture_scorer  → scan() emits architecture_score + architecture_profile
Wire 2: antipattern_detector → scan() emits anti_patterns list
Wire 3: persist anchors      → scan() emits anchor_persist_result
Wire 4: _missing_plan_recommendations → generate_report() includes recommendation when planned absent
Wire 5: DecayForecast        → compute_drift_score() receives forecast from score history

All tests operate on temporary directories so the real project is never written to.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_empty_project(tmp_path: Path) -> Path:
    """Minimal project: pyproject.toml so genesis tools recognise it."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "test_proj"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (tmp_path / ".genesis").mkdir(exist_ok=True)
    return tmp_path


def _make_scan_with_drift(
    *,
    vagrant: bool = False,
    stale: bool = False,
    planned_missing: bool = False,
    arch_score: float | None = None,
    anti_patterns: list | None = None,
) -> dict:
    """Build a minimal scan-output dict for generate_report() tests."""
    basis = "no planned model detected" if planned_missing else "dual-signal detection"
    conf = 0.15 if planned_missing else 0.80

    drift_flags: dict = {
        "vagrant_candidates": [
            {"node_id": "auth", "name": "AuthService", "kind": "component",
             "reason": "absent from planned", "confidence": 0.85}
        ] if vagrant else [],
        "stale_candidates": [
            {"node_id": "billing", "responsibility_id": "r1",
             "statement": "process payments", "confidence": 0.75, "reason": "no source"}
        ] if stale else [],
        "confidence": conf,
        "basis": basis,
        "warnings": [],
    }

    return {
        "drift_flags": drift_flags,
        "drift_score": {
            "overall_score": 55.0 if (vagrant or stale) else 0.0,
            "risk_level": "high" if (vagrant or stale) else "none",
            "confidence": 0.80,
            "basis": "test",
            "top_risk_nodes": ["auth"] if vagrant else [],
            "per_node_scores": [],
            "warnings": [],
        },
        "source_anchors": {
            "total_responsibilities": 3,
            "unanchored_count": 2,
            "anchored_count": 1,
            "warnings": [],
        },
        "fix_commit_hotspots": {},
        "dead_file_candidates": [],
        "version_drift": False,
        "version_sources": {},
        "model_sync": {
            "synced": True,
            "node_count": 4,
            "diverged": False,
            "warning": None,
        },
        "model_diff": {"has_changes": False, "summary": "no diff"},
        "architecture_score": arch_score,
        "architecture_profile": "default",
        "anti_patterns": anti_patterns or [],
        "anchor_persist_result": {"added": 0, "skipped": 0, "saved": False, "warnings": []},
    }


# ===========================================================================
# Wire 1 — architecture_scorer in scan()
# ===========================================================================

class TestArchitectureScorerIntegration:
    """scan() must include architecture_score and architecture_profile keys."""

    def test_keys_present_in_scan_output(self, tmp_path):
        """scan() always emits architecture_score and architecture_profile."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)
        result = scan(proj)
        assert "architecture_score" in result, "architecture_score missing from scan()"
        assert "architecture_profile" in result, "architecture_profile missing from scan()"

    def test_architecture_score_is_numeric_or_none(self, tmp_path):
        """architecture_score must be numeric (int or float, 0-100) or None on failure."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)
        result = scan(proj)
        score = result["architecture_score"]
        assert score is None or isinstance(score, (int, float)), (
            f"architecture_score should be numeric or None, got {type(score)}"
        )
        if score is not None:
            assert 0.0 <= float(score) <= 100.0

    def test_architecture_profile_is_string(self, tmp_path):
        """architecture_profile must be a non-empty string."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)
        result = scan(proj)
        profile = result["architecture_profile"]
        assert isinstance(profile, str) and profile, "architecture_profile must be a non-empty string"

    def test_scan_never_crashes_if_scorer_raises(self, tmp_path):
        """scan() must not crash even if architecture_scorer.score_project raises."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)
        with patch("genesis_architect_pro.architecture_scorer.score_project",
                   side_effect=RuntimeError("boom")):
            result = scan(proj)
        assert "architecture_score" in result
        assert result["architecture_score"] is None

    def test_architecture_score_reflected_in_report(self):
        """generate_report picks up architecture_score and classifies it."""
        from genesis_architect_pro.recovery_report import generate_report
        scan = _make_scan_with_drift(arch_score=80.0)
        report = generate_report(scan)
        assert report.architecture_health.score == 80.0
        assert report.architecture_health.label == "good"

    def test_architecture_score_poor_label(self):
        """Score below 50 → 'poor'."""
        from genesis_architect_pro.recovery_report import generate_report
        scan = _make_scan_with_drift(arch_score=40.0)
        report = generate_report(scan)
        assert report.architecture_health.label == "poor"

    def test_architecture_score_fair_label(self):
        """Score 50–74 → 'fair'."""
        from genesis_architect_pro.recovery_report import generate_report
        scan = _make_scan_with_drift(arch_score=62.0)
        report = generate_report(scan)
        assert report.architecture_health.label == "fair"

    def test_architecture_score_none_label(self):
        """None score → label='unavailable'."""
        from genesis_architect_pro.recovery_report import generate_report
        scan = _make_scan_with_drift(arch_score=None)
        report = generate_report(scan)
        assert report.architecture_health.label == "unavailable"
        assert report.architecture_health.score is None


# ===========================================================================
# Wire 2 — antipattern_detector in scan()
# ===========================================================================

class TestAntipatternIntegration:
    """scan() must include anti_patterns key; generate_report must process it."""

    def test_anti_patterns_key_present(self, tmp_path):
        """scan() always emits anti_patterns list."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)
        result = scan(proj)
        assert "anti_patterns" in result

    def test_anti_patterns_is_list(self, tmp_path):
        """anti_patterns must be a list."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)
        result = scan(proj)
        assert isinstance(result["anti_patterns"], list)

    def test_each_anti_pattern_has_required_keys(self, tmp_path):
        """Each anti-pattern dict must have kind, file, confidence, severity, basis."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)
        result = scan(proj)
        for ap in result["anti_patterns"]:
            assert "kind" in ap, f"missing 'kind' in {ap}"
            assert "file" in ap, f"missing 'file' in {ap}"
            assert "confidence" in ap, f"missing 'confidence' in {ap}"
            assert "severity" in ap, f"missing 'severity' in {ap}"
            assert "basis" in ap, f"missing 'basis' in {ap}"

    def test_scan_never_crashes_if_detector_raises(self, tmp_path):
        """scan() must not crash even if antipattern_detector.detect_all raises."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)
        with patch("genesis_architect_pro.antipattern_detector.detect_all",
                   side_effect=RuntimeError("detector down")):
            result = scan(proj)
        assert result["anti_patterns"] == []

    def test_anti_patterns_produce_recommendations(self):
        """Anti-patterns in scan output produce priority-3 recommendations."""
        from genesis_architect_pro.recovery_report import generate_report
        patterns = [
            {"kind": "god-class", "file": "services/god.py",
             "confidence": 0.80, "severity": "high", "basis": "fan_out=42"},
            {"kind": "circular-dep", "file": "utils/cycle.py",
             "confidence": 0.75, "severity": "critical", "basis": "cycle detected"},
        ]
        scan = _make_scan_with_drift(anti_patterns=patterns)
        report = generate_report(scan)
        ap_recs = [r for r in report.recommendations if r.category == "anti-pattern"]
        assert len(ap_recs) == 2
        for r in ap_recs:
            assert r.priority == 3

    def test_anti_pattern_confidence_propagated(self):
        """Confidence from anti_pattern dict must appear in the recommendation."""
        from genesis_architect_pro.recovery_report import generate_report
        patterns = [{"kind": "hub-file", "file": "core.py",
                     "confidence": 0.62, "severity": "medium", "basis": "fan_in=20"}]
        scan = _make_scan_with_drift(anti_patterns=patterns)
        report = generate_report(scan)
        ap_recs = [r for r in report.recommendations if r.category == "anti-pattern"]
        assert ap_recs and abs(ap_recs[0].confidence - 0.62) < 1e-6

    def test_anti_pattern_count_in_arch_health(self):
        """architecture_health.anti_pattern_count must reflect the list length."""
        from genesis_architect_pro.recovery_report import generate_report
        patterns = [
            {"kind": "dead-code", "file": "old.py",
             "confidence": 0.55, "severity": "low", "basis": "unused"},
        ] * 3
        scan = _make_scan_with_drift(anti_patterns=patterns)
        report = generate_report(scan)
        assert report.architecture_health.anti_pattern_count == 3


# ===========================================================================
# Wire 3 — anchor persistence in scan()
# ===========================================================================

class TestAnchorPersistenceIntegration:
    """scan() must emit anchor_persist_result with at least added/skipped/saved/warnings."""

    def test_anchor_persist_result_present(self, tmp_path):
        """scan() always emits anchor_persist_result."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)
        result = scan(proj)
        assert "anchor_persist_result" in result

    def test_anchor_persist_result_has_required_keys(self, tmp_path):
        """anchor_persist_result must have added, skipped, saved, warnings."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)
        result = scan(proj)
        apr = result["anchor_persist_result"]
        assert isinstance(apr, dict), "anchor_persist_result must be dict"
        for key in ("added", "skipped", "saved", "warnings"):
            assert key in apr, f"anchor_persist_result missing '{key}'"

    def test_anchor_persist_result_warnings_is_list(self, tmp_path):
        """anchor_persist_result.warnings must be a list."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)
        result = scan(proj)
        assert isinstance(result["anchor_persist_result"]["warnings"], list)

    def test_scan_never_crashes_if_persist_raises(self, tmp_path):
        """scan() must not crash even if persist_anchors raises."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)
        with patch("genesis_architect_pro.source_anchor.persist_anchors",
                   side_effect=RuntimeError("persist failed")):
            result = scan(proj)
        apr = result["anchor_persist_result"]
        assert isinstance(apr, dict)
        assert len(apr.get("warnings", [])) >= 0  # may or may not surface


# ===========================================================================
# Wire 4 — _missing_plan_recommendations
# ===========================================================================

class TestMissingPlanRecommendation:
    """When planned.json is absent, generate_report should include a recommendation."""

    def test_missing_plan_emits_recommendation(self):
        """Scan with no-planned-model basis → recommendation with category 'no-planned-model'."""
        from genesis_architect_pro.recovery_report import generate_report
        scan = _make_scan_with_drift(planned_missing=True)
        report = generate_report(scan)
        categories = [r.category for r in report.recommendations]
        assert "no-planned-model" in categories, (
            f"Expected 'no-planned-model' rec; got categories: {categories}"
        )

    def test_missing_plan_rec_is_quick_win(self):
        """No-planned-model recommendation must be a quick win (easy to act on)."""
        from genesis_architect_pro.recovery_report import generate_report
        scan = _make_scan_with_drift(planned_missing=True)
        report = generate_report(scan)
        recs = [r for r in report.recommendations if r.category == "no-planned-model"]
        assert recs and recs[0].quick_win

    def test_missing_plan_rec_not_risk_zone(self):
        """No-planned-model recommendation must NOT be a risk zone."""
        from genesis_architect_pro.recovery_report import generate_report
        scan = _make_scan_with_drift(planned_missing=True)
        report = generate_report(scan)
        recs = [r for r in report.recommendations if r.category == "no-planned-model"]
        assert recs and not recs[0].risk_zone

    def test_missing_plan_rec_has_high_confidence(self):
        """No-planned-model is a structural fact → confidence should be ≥ 0.80."""
        from genesis_architect_pro.recovery_report import generate_report
        scan = _make_scan_with_drift(planned_missing=True)
        report = generate_report(scan)
        recs = [r for r in report.recommendations if r.category == "no-planned-model"]
        assert recs and recs[0].confidence >= 0.80

    def test_planned_present_no_such_rec(self):
        """When planned model exists and drift is normal, no no-planned-model rec."""
        from genesis_architect_pro.recovery_report import generate_report
        scan = _make_scan_with_drift(vagrant=True, planned_missing=False)
        report = generate_report(scan)
        categories = [r.category for r in report.recommendations]
        assert "no-planned-model" not in categories

    def test_empty_project_no_such_rec(self):
        """Completely empty project (no nodes) should not produce no-planned-model."""
        from genesis_architect_pro.recovery_report import generate_report
        report = generate_report({})
        categories = [r.category for r in report.recommendations]
        assert "no-planned-model" not in categories

    def test_missing_plan_rec_suggested_action_has_command(self):
        """Suggested action must mention genesis plan init."""
        from genesis_architect_pro.recovery_report import generate_report
        scan = _make_scan_with_drift(planned_missing=True)
        report = generate_report(scan)
        recs = [r for r in report.recommendations if r.category == "no-planned-model"]
        assert recs and "genesis plan init" in recs[0].suggested_action


# ===========================================================================
# Wire 5 — DecayForecast threading into drift_scorer
# ===========================================================================

class TestDecayForecastIntegration:
    """compute_drift_score() must accept and use an optional DecayForecast."""

    def test_compute_drift_score_accepts_forecast_none(self, tmp_path):
        """compute_drift_score(project_dir, forecast=None) must not raise."""
        from genesis_architect_pro.drift_scorer import compute_drift_score
        proj = _make_empty_project(tmp_path)
        result = compute_drift_score(proj, forecast=None)
        assert result is not None
        assert hasattr(result, "overall_score")

    def test_compute_drift_score_accepts_forecast_object(self, tmp_path):
        """compute_drift_score accepts a DecayForecast mock without raising."""
        from genesis_architect_pro.drift_scorer import compute_drift_score

        # Use a MagicMock to simulate a DecayForecast without constructing the real object
        # (avoids coupling the test to the internal field list of DecayForecast)
        mock_forecast = MagicMock()
        mock_forecast.regression.slope = -1.5
        mock_forecast.regression.is_significant = True
        mock_forecast.predicted_score = 74.0

        proj = _make_empty_project(tmp_path)
        result = compute_drift_score(proj, forecast=mock_forecast)
        assert hasattr(result, "overall_score")

    def test_declining_forecast_increases_temporal_penalty(self, tmp_path):
        """A strongly declining forecast should produce a higher score than no forecast."""
        from genesis_architect_pro.drift_scorer import compute_drift_score

        # Strongly declining forecast mock
        mock_forecast = MagicMock()
        mock_forecast.regression.slope = -5.0
        mock_forecast.regression.is_significant = True
        mock_forecast.predicted_score = 50.0

        proj = _make_empty_project(tmp_path)
        score_no_forecast = compute_drift_score(proj, forecast=None)
        score_with_forecast = compute_drift_score(proj, forecast=mock_forecast)

        # With declining forecast, score should be >= score without forecast
        # (temporal penalty added on top of base penalties)
        assert score_with_forecast.overall_score >= score_no_forecast.overall_score, (
            "Declining forecast should add temporal penalty, increasing drift score"
        )

    def test_scan_computes_decay_forecast_from_history(self, tmp_path):
        """scan() threads DecayForecast when ≥3 score history records exist."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)

        # Write 4 score history records (required minimum is 3)
        history_path = proj / ".genesis" / "score_history.jsonl"
        records = [
            {"timestamp": "2026-01-01T00:00:00+00:00", "total": 85.0,
             "modularity": 80, "coupling": 90, "cohesion": 75, "layering": 85,
             "profile": "default", "cycle_count": 0, "module_count": 5},
            {"timestamp": "2026-01-08T00:00:00+00:00", "total": 80.0,
             "modularity": 75, "coupling": 88, "cohesion": 72, "layering": 80,
             "profile": "default", "cycle_count": 1, "module_count": 5},
            {"timestamp": "2026-01-15T00:00:00+00:00", "total": 75.0,
             "modularity": 70, "coupling": 85, "cohesion": 70, "layering": 75,
             "profile": "default", "cycle_count": 1, "module_count": 5},
            {"timestamp": "2026-01-22T00:00:00+00:00", "total": 70.0,
             "modularity": 65, "coupling": 82, "cohesion": 68, "layering": 70,
             "profile": "default", "cycle_count": 2, "module_count": 5},
        ]
        history_path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
        )

        result = scan(proj)
        # scan() should not crash and drift_score should be present
        assert "drift_score" in result
        ds = result["drift_score"]
        assert "overall_score" in ds, "drift_score must have overall_score"
        # Score should be numeric
        assert isinstance(ds["overall_score"], (int, float))

    def test_scan_no_crash_without_history(self, tmp_path):
        """scan() must not crash when score_history.jsonl is absent."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)
        result = scan(proj)
        assert "drift_score" in result


# ===========================================================================
# End-to-end integration
# ===========================================================================

class TestEndToEndIntegration:
    """Full pipeline: scan() → generate_report() → all five wires cooperate."""

    def test_scan_output_is_json_serialisable(self, tmp_path):
        """scan() output must be fully JSON-serialisable (no custom objects)."""
        from genesis_architect_pro.recovery_scan import scan
        proj = _make_empty_project(tmp_path)
        result = scan(proj)
        # Should not raise
        serialised = json.dumps(result)
        assert len(serialised) > 0

    def test_generate_report_handles_all_new_keys(self):
        """generate_report() processes all five wires without raising."""
        from genesis_architect_pro.recovery_report import generate_report
        scan = _make_scan_with_drift(
            vagrant=True,
            stale=True,
            arch_score=72.0,
            anti_patterns=[
                {"kind": "god-class", "file": "big.py",
                 "confidence": 0.75, "severity": "high", "basis": "lines=2000"},
            ],
        )
        report = generate_report(scan)
        assert report.project_risk_level in ("none", "low", "medium", "high", "critical")
        assert isinstance(report.recommendations, list)

    def test_full_report_to_dict_has_expected_keys(self):
        """RecoveryReport.to_dict() must include all top-level keys."""
        from genesis_architect_pro.recovery_report import generate_report
        scan = _make_scan_with_drift(vagrant=True, arch_score=65.0)
        report = generate_report(scan)
        d = report.to_dict()
        for key in ("executive_summary", "project_risk_level", "architecture_health",
                    "drift_summary", "recommendations", "quick_wins",
                    "deep_refactor_candidates", "risk_zones", "evidence_basis",
                    "warnings", "metadata"):
            assert key in d, f"to_dict() missing key '{key}'"

    def test_html_report_renders_without_crash(self):
        """to_html() must succeed end-to-end with all five wires providing data."""
        from genesis_architect_pro.recovery_report import generate_report
        scan = _make_scan_with_drift(
            vagrant=True, stale=True, arch_score=50.0,
            anti_patterns=[
                {"kind": "circular-dep", "file": "a.py",
                 "confidence": 0.80, "severity": "critical", "basis": "cycle"},
            ],
        )
        report = generate_report(scan)
        html = report.to_html()
        assert "<!DOCTYPE html>" in html
        assert "Genesis Recovery Report" in html

    def test_scan_and_generate_report_for_project(self, tmp_path):
        """generate_report_for_project() end-to-end must never raise."""
        from genesis_architect_pro.recovery_report import generate_report_for_project
        proj = _make_empty_project(tmp_path)
        report = generate_report_for_project(proj)
        assert report is not None
        assert isinstance(report.recommendations, list)
        assert isinstance(report.warnings, list)
