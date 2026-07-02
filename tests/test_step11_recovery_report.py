"""
Tests for recovery_report — Step 11.

Covers:
  generate_report():
    - empty scan → valid clean report, no crash
    - healthy project scan → risk level low/none
    - high drift project → risk level high/critical
    - stale-only project → stale recommendations present
    - vagrant-only project → vagrant recommendations present
    - missing scan inputs → graceful degradation, warnings emitted
    - recommendation ordering (priority ASC, confidence DESC, title ASC)
    - confidence propagation from drift signals to recommendations
    - all recommendation fields populated
    - quick_wins property correct
    - risk_zones property correct
    - deep_refactor_candidates property correct
    - executive_summary is non-empty string
    - evidence_basis populated for available signals
    - metadata.scan_keys_missing populated for absent keys
    - drift summary mirrors drift_score and drift_flags
    - architecture_health mirrors scan inputs
    - version drift → version-drift recommendation
    - churn hotspots ≥ 3 → churn recommendation
    - churn hotspots < 3 → no churn recommendation
    - dead file candidates → dead-file recommendations
    - anti_patterns key → anti-pattern recommendations
    - JSON serialisation
    - Markdown rendering (key headers present)
    - deterministic output on repeated calls
    - scan integration (recovery_report key present in scan output)
    - all legacy scan keys unchanged after adding recovery_report
    - empty project scan produces valid report

  generate_report_for_project():
    - no .genesis dir → valid report, no crash
    - populated project → report produced

  Package exports:
    - RecoveryReport, generate_report, generate_report_for_project
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from genesis_architect_pro.recovery_report import (
    generate_report, generate_report_for_project,
    RecoveryReport,
)
from genesis_architect_pro.recovery_scan import scan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vagrant_scan(n: int = 1, conf: float = 0.80) -> dict:
    return {
        "drift_flags": {
            "vagrant_candidates": [
                {"node_id": f"node{i}", "name": f"Node{i}",
                 "kind": "component", "reason": "missing", "confidence": conf}
                for i in range(n)
            ],
            "stale_candidates": [],
            "confidence": 0.80, "basis": "test", "warnings": [],
        },
        "drift_score": {
            "overall_score": 20.0 * n, "risk_level": "medium" if n < 3 else "high",
            "confidence": 0.80, "basis": "test",
            "top_risk_nodes": [f"node{i}" for i in range(n)],
            "per_node_scores": [], "warnings": [],
        },
        "source_anchors": {
            "total_responsibilities": 0, "unanchored_count": 0,
            "anchored_count": 0, "warnings": [],
        },
    }


def _stale_scan(n: int = 1, conf: float = 0.75) -> dict:
    return {
        "drift_flags": {
            "vagrant_candidates": [],
            "stale_candidates": [
                {"node_id": f"n{i}", "responsibility_id": f"r{i}",
                 "statement": f"responsibility {i}", "reason": "no source", "confidence": conf}
                for i in range(n)
            ],
            "confidence": 0.75, "basis": "test", "warnings": [],
        },
        "drift_score": {
            "overall_score": 10.0 * n, "risk_level": "low",
            "confidence": 0.75, "basis": "test",
            "top_risk_nodes": [], "per_node_scores": [], "warnings": [],
        },
        "source_anchors": {
            "total_responsibilities": n, "unanchored_count": n,
            "anchored_count": 0, "warnings": [],
        },
    }


def _full_scan() -> dict:
    s = _vagrant_scan(2, 0.80)
    s.update(_stale_scan(2, 0.70))  # merge
    s["fix_commit_hotspots"] = {"src/main.py": 5, "src/utils.py": 3, "src/old.py": 1}
    s["dead_file_candidates"] = ["src/orphan.py"]
    s["version_sources"] = {"pyproject.toml": "1.0.0", "package.json": "1.1.0"}
    s["version_drift"] = True
    return s


def _make_python_project(root: Path) -> None:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[tool.poetry]\nname='testproject'\n")
    (src / "mod.py").write_text("X = 0\n")
    (root / ".git").mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# generate_report — empty scan
# ---------------------------------------------------------------------------

class TestEmptyScan:
    def test_empty_scan_no_crash(self):
        r = generate_report({})
        assert isinstance(r, RecoveryReport)

    def test_empty_scan_risk_none(self):
        r = generate_report({})
        assert r.project_risk_level == "none"

    def test_empty_scan_no_recommendations(self):
        r = generate_report({})
        assert r.recommendations == []

    def test_empty_scan_executive_summary_non_empty(self):
        r = generate_report({})
        assert isinstance(r.executive_summary, str)
        assert len(r.executive_summary) > 0

    def test_empty_scan_missing_keys_reported(self):
        r = generate_report({})
        assert len(r.metadata.scan_keys_missing) > 0

    def test_empty_scan_valid_architecture_health(self):
        r = generate_report({})
        ah = r.architecture_health
        assert ah.score is None
        assert ah.label == "unavailable"

    def test_empty_scan_valid_drift_summary(self):
        r = generate_report({})
        ds = r.drift_summary
        assert ds.overall_score == 0.0
        assert ds.vagrant_count == 0


# ---------------------------------------------------------------------------
# generate_report — healthy project
# ---------------------------------------------------------------------------

class TestHealthyProject:
    def _healthy_scan(self) -> dict:
        return {
            "fix_commit_hotspots": {"src/a.py": 1},
            "version_sources": {"pyproject.toml": "1.0.0"},
            "version_drift": False,
            "dead_file_candidates": [],
            "drift_flags": {
                "vagrant_candidates": [],
                "stale_candidates": [],
                "confidence": 0.85, "basis": "clean", "warnings": [],
            },
            "drift_score": {
                "overall_score": 0.0, "risk_level": "none",
                "confidence": 0.85, "basis": "no drift",
                "top_risk_nodes": [], "per_node_scores": [], "warnings": [],
            },
            "source_anchors": {
                "total_responsibilities": 5, "unanchored_count": 0,
                "anchored_count": 5, "warnings": [],
            },
        }

    def test_healthy_risk_none_or_low(self):
        r = generate_report(self._healthy_scan())
        assert r.project_risk_level in ("none", "low")

    def test_healthy_no_vagrant_recs(self):
        r = generate_report(self._healthy_scan())
        assert not any(rec.category == "vagrant" for rec in r.recommendations)

    def test_healthy_no_stale_recs(self):
        r = generate_report(self._healthy_scan())
        assert not any(rec.category == "stale" for rec in r.recommendations)


# ---------------------------------------------------------------------------
# generate_report — high drift project
# ---------------------------------------------------------------------------

class TestHighDriftProject:
    def test_high_drift_risk_elevated(self):
        r = generate_report(_vagrant_scan(3, 0.85))
        assert r.project_risk_level in ("medium", "high", "critical")

    def test_high_drift_vagrant_recs_present(self):
        r = generate_report(_vagrant_scan(3, 0.85))
        assert any(rec.category == "vagrant" for rec in r.recommendations)

    def test_high_drift_first_rec_is_vagrant(self):
        r = generate_report(_vagrant_scan(2, 0.85))
        assert r.recommendations[0].category == "vagrant"

    def test_high_drift_summary_matches_input(self):
        scan = _vagrant_scan(3, 0.85)
        r = generate_report(scan)
        assert r.drift_summary.vagrant_count == 3


# ---------------------------------------------------------------------------
# generate_report — stale-only
# ---------------------------------------------------------------------------

class TestStaleOnly:
    def test_stale_recs_present(self):
        r = generate_report(_stale_scan(2, 0.75))
        assert any(rec.category == "stale" for rec in r.recommendations)

    def test_stale_high_conf_high_priority(self):
        r = generate_report(_stale_scan(1, 0.80))
        stale = [rec for rec in r.recommendations if rec.category == "stale"]
        assert stale[0].priority <= 3

    def test_stale_low_conf_lower_priority(self):
        r = generate_report(_stale_scan(1, 0.40))
        stale = [rec for rec in r.recommendations if rec.category == "stale"]
        assert stale[0].priority >= 5

    def test_stale_summary_count(self):
        r = generate_report(_stale_scan(3))
        assert r.drift_summary.stale_count == 3


# ---------------------------------------------------------------------------
# generate_report — vagrant-only
# ---------------------------------------------------------------------------

class TestVagrantOnly:
    def test_vagrant_recs_present(self):
        r = generate_report(_vagrant_scan(1, 0.80))
        assert any(rec.category == "vagrant" for rec in r.recommendations)

    def test_vagrant_high_conf_priority_1(self):
        r = generate_report(_vagrant_scan(1, 0.80))
        vagrant_recs = [rec for rec in r.recommendations if rec.category == "vagrant"]
        assert vagrant_recs[0].priority == 1

    def test_vagrant_low_conf_priority_2(self):
        r = generate_report(_vagrant_scan(1, 0.40))
        vagrant_recs = [rec for rec in r.recommendations if rec.category == "vagrant"]
        assert vagrant_recs[0].priority == 2

    def test_vagrant_high_conf_in_risk_zone(self):
        r = generate_report(_vagrant_scan(1, 0.80))
        vagrant_recs = [rec for rec in r.recommendations if rec.category == "vagrant"]
        assert vagrant_recs[0].risk_zone is True

    def test_vagrant_low_conf_is_quick_win(self):
        r = generate_report(_vagrant_scan(1, 0.40))
        vagrant_recs = [rec for rec in r.recommendations if rec.category == "vagrant"]
        assert vagrant_recs[0].quick_win is True


# ---------------------------------------------------------------------------
# generate_report — missing inputs
# ---------------------------------------------------------------------------

class TestMissingInputs:
    def test_no_drift_flags_key(self):
        r = generate_report({"drift_score": {"overall_score": 0.0, "risk_level": "none",
                             "top_risk_nodes": [], "warnings": [], "confidence": 0.5, "basis": ""}})
        assert isinstance(r, RecoveryReport)

    def test_no_drift_score_key(self):
        r = generate_report({"drift_flags": {"vagrant_candidates": [], "stale_candidates": [],
                             "confidence": 0.5, "basis": "", "warnings": []}})
        assert isinstance(r, RecoveryReport)

    def test_corrupted_drift_flags(self):
        r = generate_report({"drift_flags": "NOT A DICT"})
        assert isinstance(r, RecoveryReport)
        assert r.drift_summary.vagrant_count == 0

    def test_missing_source_anchors(self):
        r = generate_report(_vagrant_scan(1))
        assert isinstance(r, RecoveryReport)

    def test_none_values_tolerated(self):
        r = generate_report({"drift_flags": None, "drift_score": None})
        assert isinstance(r, RecoveryReport)


# ---------------------------------------------------------------------------
# generate_report — recommendation ordering
# ---------------------------------------------------------------------------

class TestRecommendationOrdering:
    def test_ordered_by_priority_asc(self):
        r = generate_report(_full_scan())
        priorities = [rec.priority for rec in r.recommendations]
        assert priorities == sorted(priorities)

    def test_same_priority_ordered_by_confidence_desc(self):
        scan = {
            "drift_flags": {
                "vagrant_candidates": [
                    {"node_id": "a", "name": "A", "kind": "c", "reason": "r", "confidence": 0.60},
                    {"node_id": "b", "name": "B", "kind": "c", "reason": "r", "confidence": 0.80},
                ],
                "stale_candidates": [],
                "confidence": 0.75, "basis": "t", "warnings": [],
            },
            "drift_score": {"overall_score": 10.0, "risk_level": "low", "confidence": 0.75,
                            "basis": "t", "top_risk_nodes": [], "per_node_scores": [], "warnings": []},
            "source_anchors": {"total_responsibilities": 0, "unanchored_count": 0,
                               "anchored_count": 0, "warnings": []},
        }
        r = generate_report(scan)
        vagrant_recs = [rec for rec in r.recommendations if rec.category == "vagrant"]
        confs = [rec.confidence for rec in vagrant_recs]
        assert confs == sorted(confs, reverse=True)

    def test_same_priority_confidence_title_tiebreak(self):
        scan = {
            "drift_flags": {
                "vagrant_candidates": [
                    {"node_id": "z", "name": "Zebra", "kind": "c", "reason": "r", "confidence": 0.80},
                    {"node_id": "a", "name": "Alpha", "kind": "c", "reason": "r", "confidence": 0.80},
                ],
                "stale_candidates": [],
                "confidence": 0.80, "basis": "t", "warnings": [],
            },
            "drift_score": {"overall_score": 20.0, "risk_level": "medium", "confidence": 0.80,
                            "basis": "t", "top_risk_nodes": [], "per_node_scores": [], "warnings": []},
            "source_anchors": {"total_responsibilities": 0, "unanchored_count": 0,
                               "anchored_count": 0, "warnings": []},
        }
        r = generate_report(scan)
        vagrant_recs = [rec for rec in r.recommendations if rec.category == "vagrant"]
        titles = [rec.title for rec in vagrant_recs]
        assert titles == sorted(titles)


# ---------------------------------------------------------------------------
# generate_report — confidence propagation
# ---------------------------------------------------------------------------

class TestConfidencePropagation:
    def test_high_conf_vagrant_recommendation_confidence(self):
        r = generate_report(_vagrant_scan(1, 0.90))
        vagrant_recs = [rec for rec in r.recommendations if rec.category == "vagrant"]
        assert vagrant_recs[0].confidence == pytest.approx(0.90)

    def test_low_conf_stale_recommendation_confidence(self):
        r = generate_report(_stale_scan(1, 0.35))
        stale_recs = [rec for rec in r.recommendations if rec.category == "stale"]
        assert stale_recs[0].confidence == pytest.approx(0.35)


# ---------------------------------------------------------------------------
# generate_report — recommendation fields
# ---------------------------------------------------------------------------

class TestRecommendationFields:
    def test_all_required_fields_present(self):
        r = generate_report(_vagrant_scan(1))
        rec = r.recommendations[0]
        assert isinstance(rec.priority, int)
        assert isinstance(rec.category, str) and rec.category
        assert isinstance(rec.title, str) and rec.title
        assert isinstance(rec.reason, str) and rec.reason
        assert isinstance(rec.evidence, str) and rec.evidence
        assert isinstance(rec.confidence, float) and 0.0 <= rec.confidence <= 1.0
        assert isinstance(rec.suggested_action, str) and rec.suggested_action
        assert isinstance(rec.affected, list)
        assert isinstance(rec.risk_zone, bool)
        assert isinstance(rec.quick_win, bool)

    def test_to_dict_has_all_keys(self):
        r = generate_report(_vagrant_scan(1))
        d = r.recommendations[0].to_dict()
        for k in ("priority", "category", "title", "reason", "evidence",
                  "confidence", "suggested_action", "affected", "risk_zone", "quick_win"):
            assert k in d


# ---------------------------------------------------------------------------
# generate_report — derived properties
# ---------------------------------------------------------------------------

class TestDerivedProperties:
    def test_quick_wins_subset_of_recommendations(self):
        r = generate_report(_full_scan())
        rec_set = set(id(rec) for rec in r.recommendations)
        for qw in r.quick_wins:
            assert id(qw) in rec_set

    def test_risk_zones_subset_of_recommendations(self):
        r = generate_report(_vagrant_scan(1, 0.85))
        rec_set = set(id(rec) for rec in r.recommendations)
        for rz in r.risk_zones:
            assert id(rz) in rec_set

    def test_quick_wins_all_marked_quick_win(self):
        r = generate_report(_full_scan())
        assert all(rec.quick_win for rec in r.quick_wins)

    def test_risk_zones_all_marked_risk_zone(self):
        r = generate_report(_vagrant_scan(1, 0.85))
        assert all(rec.risk_zone for rec in r.risk_zones)

    def test_deep_refactor_not_quick_win_not_risk_zone(self):
        r = generate_report(_full_scan())
        for rec in r.deep_refactor_candidates:
            assert not rec.quick_win
            assert not rec.risk_zone
            assert rec.priority <= 3


# ---------------------------------------------------------------------------
# generate_report — signal-specific tests
# ---------------------------------------------------------------------------

class TestSpecificSignals:
    def test_version_drift_recommendation(self):
        scan = {
            "version_sources": {"a.toml": "1.0", "b.json": "2.0"},
            "version_drift": True,
        }
        r = generate_report(scan)
        assert any(rec.category == "version-drift" for rec in r.recommendations)

    def test_no_version_drift_no_rec(self):
        scan = {"version_sources": {"a.toml": "1.0"}, "version_drift": False}
        r = generate_report(scan)
        assert not any(rec.category == "version-drift" for rec in r.recommendations)

    def test_churn_hotspot_gte_3_creates_rec(self):
        scan = {"fix_commit_hotspots": {"src/a.py": 4}}
        r = generate_report(scan)
        assert any(rec.category == "churn" for rec in r.recommendations)

    def test_churn_hotspot_lt_3_no_rec(self):
        scan = {"fix_commit_hotspots": {"src/a.py": 2}}
        r = generate_report(scan)
        assert not any(rec.category == "churn" for rec in r.recommendations)

    def test_dead_file_creates_rec(self):
        scan = {"dead_file_candidates": ["src/orphan.py"]}
        r = generate_report(scan)
        assert any(rec.category == "dead-file" for rec in r.recommendations)

    def test_no_dead_files_no_rec(self):
        scan = {"dead_file_candidates": []}
        r = generate_report(scan)
        assert not any(rec.category == "dead-file" for rec in r.recommendations)

    def test_anti_patterns_creates_rec(self):
        scan = {"anti_patterns": [
            {"kind": "god-class", "file": "src/big.py",
             "confidence": 0.80, "severity": "high", "basis": "fan_out=25"}
        ]}
        r = generate_report(scan)
        assert any(rec.category == "anti-pattern" for rec in r.recommendations)

    def test_coverage_gap_creates_rec(self):
        scan = {
            "source_anchors": {
                "total_responsibilities": 10, "unanchored_count": 6,
                "anchored_count": 4, "warnings": [],
            },
        }
        r = generate_report(scan)
        assert any(rec.category == "coverage" for rec in r.recommendations)

    def test_full_coverage_no_coverage_rec(self):
        scan = {
            "source_anchors": {
                "total_responsibilities": 5, "unanchored_count": 0,
                "anchored_count": 5, "warnings": [],
            },
        }
        r = generate_report(scan)
        assert not any(rec.category == "coverage" for rec in r.recommendations)

    def test_churn_high_enough_is_risk_zone(self):
        scan = {"fix_commit_hotspots": {"src/a.py": 10}}
        r = generate_report(scan)
        churn_recs = [rec for rec in r.recommendations if rec.category == "churn"]
        assert churn_recs[0].risk_zone is True


# ---------------------------------------------------------------------------
# generate_report — architecture health
# ---------------------------------------------------------------------------

class TestArchitectureHealth:
    def test_architecture_score_reflected(self):
        scan = {"architecture_score": 80.0}
        r = generate_report(scan)
        assert r.architecture_health.score == pytest.approx(80.0)
        assert r.architecture_health.label == "good"

    def test_low_arch_score_poor_label(self):
        scan = {"architecture_score": 40.0}
        r = generate_report(scan)
        assert r.architecture_health.label == "poor"

    def test_no_arch_score_unavailable(self):
        r = generate_report({})
        assert r.architecture_health.score is None
        assert r.architecture_health.label == "unavailable"

    def test_hotspot_files_populated(self):
        scan = {"fix_commit_hotspots": {"a.py": 5, "b.py": 3}}
        r = generate_report(scan)
        assert "a.py" in r.architecture_health.hotspot_files


# ---------------------------------------------------------------------------
# generate_report — JSON serialisation
# ---------------------------------------------------------------------------

class TestJSONSerialization:
    def test_to_json_parseable(self):
        r = generate_report(_full_scan())
        parsed = json.loads(r.to_json())
        assert "executive_summary" in parsed

    def test_to_dict_all_keys_present(self):
        r = generate_report(_full_scan())
        d = r.to_dict()
        for k in ("executive_summary", "project_risk_level", "architecture_health",
                  "drift_summary", "recommendations", "quick_wins",
                  "deep_refactor_candidates", "risk_zones", "recommended_fix_order",
                  "evidence_basis", "warnings", "metadata"):
            assert k in d

    def test_recommendations_serialised_as_list(self):
        r = generate_report(_vagrant_scan(1))
        d = r.to_dict()
        assert isinstance(d["recommendations"], list)
        if d["recommendations"]:
            assert isinstance(d["recommendations"][0], dict)

    def test_json_is_valid_for_empty_scan(self):
        r = generate_report({})
        parsed = json.loads(r.to_json())
        assert parsed["project_risk_level"] == "none"


# ---------------------------------------------------------------------------
# generate_report — Markdown rendering
# ---------------------------------------------------------------------------

class TestMarkdownRendering:
    def test_markdown_has_title(self):
        r = generate_report(_full_scan())
        md = r.to_markdown()
        assert "# Genesis Recovery Report" in md

    def test_markdown_has_executive_summary(self):
        r = generate_report(_full_scan())
        md = r.to_markdown()
        assert "## Executive Summary" in md

    def test_markdown_has_drift_summary(self):
        r = generate_report(_full_scan())
        md = r.to_markdown()
        assert "## Drift Summary" in md

    def test_markdown_has_architecture_health(self):
        r = generate_report(_full_scan())
        md = r.to_markdown()
        assert "## Architecture Health" in md

    def test_markdown_has_recommendations(self):
        r = generate_report(_full_scan())
        md = r.to_markdown()
        assert "## Recommendations" in md

    def test_markdown_empty_scan_no_crash(self):
        r = generate_report({})
        md = r.to_markdown()
        assert "No recommendations" in md

    def test_markdown_risk_level_present(self):
        r = generate_report(_vagrant_scan(2, 0.85))
        md = r.to_markdown()
        assert "Project Risk Level" in md

    def test_markdown_quick_wins_section(self):
        scan = {"dead_file_candidates": ["f.py"], "version_drift": False}
        r = generate_report(scan)
        md = r.to_markdown()
        if r.quick_wins:
            assert "Quick Wins" in md

    def test_markdown_risk_zone_section(self):
        r = generate_report(_vagrant_scan(1, 0.85))
        md = r.to_markdown()
        if r.risk_zones:
            assert "Do-Not-Touch" in md


# ---------------------------------------------------------------------------
# generate_report — determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_output_repeated_calls(self):
        scan = _full_scan()
        r1 = generate_report(scan)
        r2 = generate_report(scan)
        assert r1.to_json() == r2.to_json()

    def test_recommendation_order_deterministic(self):
        scan = _full_scan()
        r1 = generate_report(scan)
        r2 = generate_report(scan)
        assert [rec.title for rec in r1.recommendations] == [rec.title for rec in r2.recommendations]


# ---------------------------------------------------------------------------
# generate_report_for_project()
# ---------------------------------------------------------------------------

class TestGenerateReportForProject:
    def test_no_genesis_dir_no_crash(self, tmp_path):
        r = generate_report_for_project(tmp_path)
        assert isinstance(r, RecoveryReport)

    def test_no_genesis_dir_produces_valid_report(self, tmp_path):
        r = generate_report_for_project(tmp_path)
        assert r.project_risk_level in ("none", "low", "medium", "high", "critical")

    def test_python_project_no_crash(self, tmp_path):
        _make_python_project(tmp_path)
        r = generate_report_for_project(tmp_path)
        assert isinstance(r, RecoveryReport)


# ---------------------------------------------------------------------------
# scan() integration
# ---------------------------------------------------------------------------

class TestScanIntegration:
    def test_recovery_report_key_present(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert "recovery_report" in result

    def test_recovery_report_has_executive_summary(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert "executive_summary" in result["recovery_report"]

    def test_recovery_report_has_project_risk_level(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        rpt = result["recovery_report"]
        assert "project_risk_level" in rpt
        assert rpt["project_risk_level"] in ("none", "low", "medium", "high", "critical")

    def test_all_legacy_keys_still_present(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        for k in ("fix_commit_hotspots", "external_url_count", "version_sources",
                  "doc_version", "version_drift", "dead_file_candidates",
                  "model_sync", "model_diff", "drift_flags",
                  "source_anchors", "drift_score", "recovery_report"):
            assert k in result, f"Missing key: {k!r}"

    def test_scan_result_json_serialisable(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        dumped = json.dumps(result)
        parsed = json.loads(dumped)
        assert "recovery_report" in parsed

    def test_scan_does_not_write_model_json(self, tmp_path):
        _make_python_project(tmp_path)
        scan(tmp_path)  # first run creates model.json
        before = (tmp_path / ".genesis" / "model.json").read_text()
        scan(tmp_path)
        after = (tmp_path / ".genesis" / "model.json").read_text()
        assert before == after

    def test_scan_does_not_create_planned_json(self, tmp_path):
        _make_python_project(tmp_path)
        scan(tmp_path)
        assert not (tmp_path / ".genesis" / "planned.json").exists()

    def test_recovery_report_warnings_is_list(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert isinstance(result["recovery_report"].get("warnings", []), list)

    def test_recovery_report_recommendations_is_list(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert isinstance(result["recovery_report"].get("recommendations", []), list)


# ---------------------------------------------------------------------------
# Package exports
# ---------------------------------------------------------------------------

class TestPackageExports:
    def test_recovery_report_class_exported(self):
        from genesis_architect_pro import RecoveryReport
        assert RecoveryReport is not None

    def test_generate_report_exported(self):
        from genesis_architect_pro import generate_report
        assert callable(generate_report)

    def test_generate_report_for_project_exported(self):
        from genesis_architect_pro import generate_report_for_project
        assert callable(generate_report_for_project)

    def test_recommendation_exported(self):
        from genesis_architect_pro import Recommendation
        assert Recommendation is not None

    def test_drift_summary_exported(self):
        from genesis_architect_pro import DriftSummary
        assert DriftSummary is not None
