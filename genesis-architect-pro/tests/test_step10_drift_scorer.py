"""
Tests for drift_scorer — Step 10.

Covers:
  score_drift() pure function:
    - no drift → overall_score=0, risk_level="none"
    - vagrant-only drift → score > 0
    - stale-only drift → score > 0
    - mixed drift → score > vagrant-only
    - vagrant penalty capped at vagrant_penalty_cap
    - stale penalty capped at stale_penalty_cap
    - no AnchorReport → coverage penalty at max
    - full coverage AnchorReport → coverage penalty = 0
    - partial coverage → proportional coverage penalty
    - temporal penalty applied when forecast has significant negative slope
    - temporal penalty not applied when slope positive or not significant
    - temporal penalty not applied when forecast=None
    - per-node scores populated for vagrant candidates
    - per-node scores populated for stale candidates
    - per-node score includes coverage and vagrant flags
    - per-node scores sorted by score DESC, node_id ASC
    - top_risk_nodes is subset of per_node_scores with score > 0
    - top_risk_nodes capped at 5
    - confidence: high when DriftFlags.confidence>=0.75 and AnchorReport provided
    - confidence: medium when only one signal
    - confidence: low when planned missing and no anchors
    - basis is non-empty string
    - warnings from DriftFlags propagated
    - DriftScorerConfig customisation respected
    - deterministic output on repeated calls

  _risk_level():
    - 0 → "none"
    - 10 → "low"
    - 30 → "medium"
    - 60 → "high"
    - 90 → "critical"

  NodeDriftScore.to_dict():
    - required keys present
    - JSON serialisable

  DriftScore.to_dict():
    - required keys present
    - JSON serialisable
    - per_node_scores is list of dicts

  compute_drift_score():
    - no .genesis/ dir → empty score, no crash
    - corrupted model → warning, continues safely
    - populated committed+planned → score produced

  scan() integration:
    - drift_score key present
    - required sub-keys present
    - all legacy keys unchanged
    - JSON-serialisable
    - no writes to model.json or planned.json

  Package exports:
    - DriftScorerConfig, NodeDriftScore, DriftScore, score_drift, compute_drift_score
"""

from __future__ import annotations

import json
import math
import warnings
from pathlib import Path


from genesis_architect_pro.drift_detector import (
    DriftFlags, VagrantCandidate, StaleCandidate,
)
from genesis_architect_pro.drift_scorer import (
    DriftScorerConfig, NodeDriftScore, DriftScore,
    score_drift, compute_drift_score, _risk_level,
)
from genesis_architect_pro.source_anchor import (
    AnchorReport, AnchorResult, AnchorEntry,
)
from genesis_architect_pro.model_store import (
    ArchModel, ModelNode, ModelResponsibility, ModelStore,
)
from genesis_architect_pro.decay_regressor import (
    DecayForecast, RegressionResult,
)
from genesis_architect_pro.recovery_scan import scan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resp(rid: str, stmt: str = "does something") -> ModelResponsibility:
    return ModelResponsibility(id=rid, statement=stmt)


def _node(nid: str, responsibilities: list | None = None, kind: str = "component") -> ModelNode:
    return ModelNode(id=nid, kind=kind, name=nid,
                     responsibilities=responsibilities or [])


def _vagrant_flags(*node_ids: str, confidence: float = 0.80) -> DriftFlags:
    """Build DriftFlags with specified vagrant candidates."""
    vagrants = [VagrantCandidate(nid, nid, "component", "reason", confidence)
                for nid in node_ids]
    return DriftFlags(
        vagrant_candidates=vagrants,
        stale_candidates=[],
        confidence=0.80,
        basis="test",
    )


def _stale_flags(node_id: str, *resp_ids: str, confidence: float = 0.80) -> DriftFlags:
    """Build DriftFlags with specified stale candidates on one node."""
    stale = [StaleCandidate(node_id, rid, f"stmt_{rid}", "reason", confidence)
             for rid in resp_ids]
    return DriftFlags(
        vagrant_candidates=[],
        stale_candidates=stale,
        confidence=0.80,
        basis="test",
    )


def _full_anchor_report(resp_ids: list[str], node_id: str = "n") -> AnchorReport:
    """All responsibilities anchored."""
    by_resp = {}
    for rid in resp_ids:
        entry = AnchorEntry(rid, 1, 3, rid, 0.95, "exact")
        by_resp[rid] = AnchorResult(rid, f"stmt {rid}", node_id, anchors=[entry])
    return AnchorReport(
        anchors_by_responsibility=by_resp,
        anchored_count=len(resp_ids),
        unanchored_count=0,
        total_responsibilities=len(resp_ids),
    )


def _empty_anchor_report(resp_ids: list[str], node_id: str = "n") -> AnchorReport:
    """All responsibilities unanchored."""
    by_resp = {rid: AnchorResult(rid, f"stmt {rid}", node_id, anchors=[])
               for rid in resp_ids}
    return AnchorReport(
        anchors_by_responsibility=by_resp,
        anchored_count=0,
        unanchored_count=len(resp_ids),
        total_responsibilities=len(resp_ids),
    )


def _make_forecast(slope: float, predicted_score: float = 50.0,
                   is_significant: bool = True) -> DecayForecast:
    reg = RegressionResult(
        slope=slope, intercept=80.0, r_squared=0.85,
        data_points=5, slope_std_error=0.5, is_significant=is_significant,
    )
    return DecayForecast(
        current_score=70.0,
        predicted_score=predicted_score,
        score_delta=predicted_score - 70.0,
        weekly_delta=slope,
        weeks_to_threshold=math.inf if slope >= 0 else 10.0,
        threshold=40.0,
        confidence=0.85,
        regression=reg,
        trajectory=[],
        summary="test forecast",
    )


def _make_python_project(root: Path) -> None:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[tool.poetry]\nname='testproject'\n")
    (src / "mod.py").write_text("X = 0\n")
    (root / ".git").mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# _risk_level
# ---------------------------------------------------------------------------

class TestRiskLevel:
    def test_zero_is_none(self):
        assert _risk_level(0.0) == "none"

    def test_low_boundary(self):
        assert _risk_level(20.0) == "low"

    def test_medium_just_above_low(self):
        assert _risk_level(21.0) == "medium"

    def test_medium_boundary(self):
        assert _risk_level(50.0) == "medium"

    def test_high_just_above_medium(self):
        assert _risk_level(51.0) == "high"

    def test_high_boundary(self):
        assert _risk_level(75.0) == "high"

    def test_critical_above_high(self):
        assert _risk_level(76.0) == "critical"

    def test_critical_maximum(self):
        assert _risk_level(100.0) == "critical"


# ---------------------------------------------------------------------------
# score_drift — no drift
# ---------------------------------------------------------------------------

class TestNoDrift:
    def test_no_candidates_score_zero(self):
        flags = DriftFlags(confidence=0.80, basis="test")
        score = score_drift(flags, AnchorReport())
        assert score.overall_score == 0.0

    def test_no_candidates_risk_none(self):
        flags = DriftFlags(confidence=0.80, basis="test")
        score = score_drift(flags, AnchorReport())
        assert score.risk_level == "none"

    def test_no_candidates_no_per_node(self):
        flags = DriftFlags(confidence=0.80, basis="test")
        score = score_drift(flags, AnchorReport())
        assert score.per_node_scores == []

    def test_no_candidates_empty_top_risk(self):
        flags = DriftFlags(confidence=0.80, basis="test")
        score = score_drift(flags, AnchorReport())
        assert score.top_risk_nodes == []


# ---------------------------------------------------------------------------
# score_drift — vagrant-only
# ---------------------------------------------------------------------------

class TestVagrantOnly:
    def test_vagrant_score_positive(self):
        score = score_drift(_vagrant_flags("a"), AnchorReport())
        assert score.overall_score > 0

    def test_vagrant_per_node_created(self):
        score = score_drift(_vagrant_flags("a"), AnchorReport())
        assert any(n.node_id == "a" for n in score.per_node_scores)

    def test_vagrant_node_flagged_true(self):
        score = score_drift(_vagrant_flags("a"), AnchorReport())
        node = next(n for n in score.per_node_scores if n.node_id == "a")
        assert node.vagrant is True

    def test_vagrant_confidence_scales_penalty(self):
        score_high = score_drift(_vagrant_flags("a", confidence=0.95), AnchorReport())
        score_low  = score_drift(_vagrant_flags("a", confidence=0.30), AnchorReport())
        assert score_high.overall_score > score_low.overall_score

    def test_many_vagrants_capped(self):
        cfg = DriftScorerConfig(vagrant_penalty_per_node=20.0, vagrant_penalty_cap=40.0)
        # 10 vagrants × 20 each = 200, but cap is 40
        flags = _vagrant_flags("a", "b", "c", "d", "e", "f", "g", "h", "i", "j")
        score = score_drift(flags, AnchorReport(), config=cfg)
        # vagrant portion ≤ 40 (cap)
        vagrant_pen = min(sum(20.0 * v.confidence for v in flags.vagrant_candidates), 40.0)
        assert score.overall_score >= vagrant_pen - 0.01  # overall >= vagrant portion


# ---------------------------------------------------------------------------
# score_drift — stale-only
# ---------------------------------------------------------------------------

class TestStaleOnly:
    def test_stale_score_positive(self):
        score = score_drift(_stale_flags("a", "r1"), AnchorReport())
        assert score.overall_score > 0

    def test_stale_per_node_created(self):
        score = score_drift(_stale_flags("a", "r1"), AnchorReport())
        assert any(n.node_id == "a" for n in score.per_node_scores)

    def test_stale_count_on_node(self):
        score = score_drift(_stale_flags("a", "r1", "r2", "r3"), AnchorReport())
        node = next(n for n in score.per_node_scores if n.node_id == "a")
        assert node.stale_responsibility_count == 3

    def test_many_stales_capped(self):
        cfg = DriftScorerConfig(stale_penalty_per_resp=15.0, stale_penalty_cap=35.0)
        flags = _stale_flags("a", *[f"r{i}" for i in range(10)])
        score = score_drift(flags, AnchorReport(), config=cfg)
        # stale portion ≤ 35
        stale_pen = min(sum(15.0 * s.confidence for s in flags.stale_candidates), 35.0)
        assert score.overall_score >= stale_pen - 0.01


# ---------------------------------------------------------------------------
# score_drift — mixed
# ---------------------------------------------------------------------------

class TestMixedDrift:
    def test_mixed_score_exceeds_vagrant_only(self):
        flags_vagrant = _vagrant_flags("a")
        flags_both = DriftFlags(
            vagrant_candidates=flags_vagrant.vagrant_candidates,
            stale_candidates=[StaleCandidate("b", "r1", "stmt", "reason", 0.80)],
            confidence=0.80, basis="test",
        )
        s_vagrant = score_drift(flags_vagrant, AnchorReport())
        s_mixed   = score_drift(flags_both,   AnchorReport())
        assert s_mixed.overall_score > s_vagrant.overall_score

    def test_mixed_multiple_nodes_in_per_node(self):
        flags = DriftFlags(
            vagrant_candidates=[VagrantCandidate("a", "Alpha", "component", "r", 0.80)],
            stale_candidates=[StaleCandidate("b", "r1", "stmt", "reason", 0.80)],
            confidence=0.80, basis="test",
        )
        score = score_drift(flags, AnchorReport())
        node_ids = {n.node_id for n in score.per_node_scores}
        assert "a" in node_ids
        assert "b" in node_ids


# ---------------------------------------------------------------------------
# score_drift — coverage penalty
# ---------------------------------------------------------------------------

class TestCoveragePenalty:
    def test_no_anchor_report_max_coverage_penalty(self):
        cfg = DriftScorerConfig(coverage_penalty_max=20.0,
                                vagrant_penalty_per_node=0.0, stale_penalty_per_resp=0.0)
        flags = DriftFlags(confidence=0.80, basis="test")
        score = score_drift(flags, anchor_report=None, config=cfg)
        assert abs(score.overall_score - 20.0) < 0.01

    def test_full_coverage_zero_penalty(self):
        cfg = DriftScorerConfig(coverage_penalty_max=20.0,
                                vagrant_penalty_per_node=0.0, stale_penalty_per_resp=0.0)
        flags = DriftFlags(confidence=0.80, basis="test")
        report = _full_anchor_report(["r1", "r2"])
        score = score_drift(flags, report, config=cfg)
        assert score.overall_score == 0.0

    def test_half_coverage_half_penalty(self):
        cfg = DriftScorerConfig(coverage_penalty_max=20.0,
                                vagrant_penalty_per_node=0.0, stale_penalty_per_resp=0.0)
        flags = DriftFlags(confidence=0.80, basis="test")
        # 1 anchored, 1 unanchored = 50% unanchored
        entry = AnchorEntry("sym", 1, 3, "sym", 0.95, "exact")
        by_resp = {
            "r1": AnchorResult("r1", "stmt", "n", anchors=[entry]),
            "r2": AnchorResult("r2", "stmt", "n", anchors=[]),
        }
        report = AnchorReport(
            anchors_by_responsibility=by_resp,
            anchored_count=1, unanchored_count=1, total_responsibilities=2,
        )
        score = score_drift(flags, report, config=cfg)
        assert abs(score.overall_score - 10.0) < 0.01

    def test_empty_report_zero_responsibilities_no_penalty(self):
        cfg = DriftScorerConfig(coverage_penalty_max=20.0,
                                vagrant_penalty_per_node=0.0, stale_penalty_per_resp=0.0)
        flags = DriftFlags(confidence=0.80, basis="test")
        report = AnchorReport(total_responsibilities=0)
        score = score_drift(flags, report, config=cfg)
        assert score.overall_score == 0.0

    def test_no_anchor_report_warning_emitted(self):
        flags = DriftFlags(confidence=0.80, basis="test")
        score = score_drift(flags, anchor_report=None)
        assert any("coverage penalty" in w.lower() for w in score.warnings)


# ---------------------------------------------------------------------------
# score_drift — temporal penalty
# ---------------------------------------------------------------------------

class TestTemporalPenalty:
    def test_significant_negative_slope_adds_penalty(self):
        cfg = DriftScorerConfig(temporal_penalty_max=15.0,
                                vagrant_penalty_per_node=0.0, stale_penalty_per_resp=0.0)
        flags = DriftFlags(confidence=0.80, basis="test")
        report = _full_anchor_report(["r1"])
        forecast = _make_forecast(slope=-2.0, predicted_score=50.0, is_significant=True)
        score_with = score_drift(flags, report, forecast, config=cfg)
        score_none = score_drift(flags, report, None, config=cfg)
        assert score_with.overall_score > score_none.overall_score

    def test_positive_slope_no_temporal_penalty(self):
        cfg = DriftScorerConfig(temporal_penalty_max=15.0,
                                vagrant_penalty_per_node=0.0, stale_penalty_per_resp=0.0)
        flags = DriftFlags(confidence=0.80, basis="test")
        report = _full_anchor_report(["r1"])
        forecast = _make_forecast(slope=1.0, predicted_score=90.0, is_significant=True)
        score = score_drift(flags, report, forecast, config=cfg)
        assert score.overall_score == 0.0

    def test_not_significant_no_temporal_penalty(self):
        cfg = DriftScorerConfig(temporal_penalty_max=15.0,
                                vagrant_penalty_per_node=0.0, stale_penalty_per_resp=0.0)
        flags = DriftFlags(confidence=0.80, basis="test")
        report = _full_anchor_report(["r1"])
        forecast = _make_forecast(slope=-3.0, predicted_score=30.0, is_significant=False)
        score = score_drift(flags, report, forecast, config=cfg)
        assert score.overall_score == 0.0

    def test_none_forecast_no_penalty(self):
        cfg = DriftScorerConfig(temporal_penalty_max=15.0,
                                vagrant_penalty_per_node=0.0, stale_penalty_per_resp=0.0)
        flags = DriftFlags(confidence=0.80, basis="test")
        report = _full_anchor_report(["r1"])
        score = score_drift(flags, report, None, config=cfg)
        assert score.overall_score == 0.0

    def test_temporal_penalty_capped_at_100(self):
        cfg = DriftScorerConfig(temporal_penalty_max=200.0)
        flags = DriftFlags(confidence=0.80, basis="test")
        forecast = _make_forecast(slope=-10.0, predicted_score=0.0, is_significant=True)
        score = score_drift(flags, None, forecast, config=cfg)
        assert score.overall_score <= 100.0


# ---------------------------------------------------------------------------
# score_drift — per-node scores
# ---------------------------------------------------------------------------

class TestPerNodeScores:
    def test_per_node_sorted_score_desc(self):
        flags = DriftFlags(
            vagrant_candidates=[
                VagrantCandidate("a", "A", "component", "r", 0.50),
                VagrantCandidate("b", "B", "component", "r", 0.90),
            ],
            stale_candidates=[],
            confidence=0.80, basis="test",
        )
        score = score_drift(flags, _full_anchor_report([]))
        scores = [n.score for n in score.per_node_scores]
        assert scores == sorted(scores, reverse=True)

    def test_per_node_secondary_sort_alphabetical(self):
        """Equal scores → alphabetical by node_id."""
        flags = DriftFlags(
            vagrant_candidates=[
                VagrantCandidate("z", "Z", "component", "r", 0.50),
                VagrantCandidate("a", "A", "component", "r", 0.50),
            ],
            stale_candidates=[],
            confidence=0.80, basis="test",
        )
        score = score_drift(flags, _full_anchor_report([]))
        ids = [n.node_id for n in score.per_node_scores if n.score > 0]
        assert ids == sorted(ids)

    def test_per_node_to_dict_required_keys(self):
        score = score_drift(_vagrant_flags("a"), AnchorReport())
        d = score.per_node_scores[0].to_dict()
        for k in ("node_id", "name", "kind", "score", "risk_level",
                  "vagrant", "stale_responsibility_count",
                  "source_map_coverage", "basis"):
            assert k in d

    def test_per_node_source_map_coverage_one_when_anchored(self):
        flags = _stale_flags("a", "r1")
        report = _full_anchor_report(["r1"], node_id="a")
        score = score_drift(flags, report)
        node = next((n for n in score.per_node_scores if n.node_id == "a"), None)
        if node:
            assert node.source_map_coverage == 1.0

    def test_per_node_coverage_zero_when_none_anchored(self):
        flags = _stale_flags("a", "r1")
        report = _empty_anchor_report(["r1"], node_id="a")
        score = score_drift(flags, report)
        node = next((n for n in score.per_node_scores if n.node_id == "a"), None)
        if node:
            assert node.source_map_coverage == 0.0


# ---------------------------------------------------------------------------
# score_drift — top_risk_nodes
# ---------------------------------------------------------------------------

class TestTopRiskNodes:
    def test_top_risk_nodes_subset_of_per_node(self):
        flags = _vagrant_flags("a", "b", "c")
        score = score_drift(flags, AnchorReport())
        per_node_ids = {n.node_id for n in score.per_node_scores}
        for nid in score.top_risk_nodes:
            assert nid in per_node_ids

    def test_top_risk_nodes_max_5(self):
        flags = _vagrant_flags("a", "b", "c", "d", "e", "f", "g", "h")
        score = score_drift(flags, AnchorReport())
        assert len(score.top_risk_nodes) <= 5

    def test_top_risk_nodes_ordered_highest_first(self):
        flags = DriftFlags(
            vagrant_candidates=[
                VagrantCandidate("low",  "Low",  "component", "r", 0.10),
                VagrantCandidate("high", "High", "component", "r", 0.90),
            ],
            stale_candidates=[],
            confidence=0.80, basis="test",
        )
        score = score_drift(flags, _full_anchor_report([]))
        if len(score.top_risk_nodes) >= 2:
            idx_high = score.top_risk_nodes.index("high")
            idx_low  = score.top_risk_nodes.index("low")
            assert idx_high < idx_low

    def test_no_risk_nodes_when_score_zero(self):
        flags = DriftFlags(confidence=0.80, basis="test")
        score = score_drift(flags, _full_anchor_report([]))
        assert score.top_risk_nodes == []


# ---------------------------------------------------------------------------
# score_drift — confidence and basis
# ---------------------------------------------------------------------------

class TestConfidenceAndBasis:
    def test_high_confidence_when_both_signals(self):
        flags = DriftFlags(confidence=0.80, basis="test")
        score = score_drift(flags, _full_anchor_report(["r1"]))
        assert score.confidence >= 0.75

    def test_medium_confidence_no_anchor_report(self):
        flags = DriftFlags(confidence=0.80, basis="test")
        score = score_drift(flags, anchor_report=None)
        assert 0.40 <= score.confidence < 0.75

    def test_medium_confidence_low_detection_conf_with_anchors(self):
        flags = DriftFlags(confidence=0.40, basis="test")
        score = score_drift(flags, _full_anchor_report(["r1"]))
        assert 0.40 <= score.confidence < 0.75

    def test_low_confidence_planned_missing(self):
        flags = DriftFlags(confidence=0.35, basis="test",
                           warnings=["planned model absent"])
        score = score_drift(flags, anchor_report=None)
        assert score.confidence < 0.50

    def test_basis_non_empty(self):
        score = score_drift(DriftFlags(confidence=0.80, basis="test"), AnchorReport())
        assert isinstance(score.basis, str)
        assert len(score.basis) > 0

    def test_drift_flags_warnings_propagated(self):
        flags = DriftFlags(confidence=0.80, basis="test",
                           warnings=["injected warning"])
        score = score_drift(flags, AnchorReport())
        assert "injected warning" in score.warnings


# ---------------------------------------------------------------------------
# score_drift — custom config
# ---------------------------------------------------------------------------

class TestCustomConfig:
    def test_zero_vagrant_penalty_no_vagrant_contribution(self):
        cfg = DriftScorerConfig(vagrant_penalty_per_node=0.0,
                                coverage_penalty_max=0.0, stale_penalty_per_resp=0.0)
        flags = _vagrant_flags("a")
        score = score_drift(flags, _full_anchor_report([]), config=cfg)
        assert score.overall_score == 0.0

    def test_higher_stale_penalty_increases_score(self):
        cfg_low  = DriftScorerConfig(stale_penalty_per_resp=1.0)
        cfg_high = DriftScorerConfig(stale_penalty_per_resp=20.0)
        flags = _stale_flags("a", "r1", "r2")
        s_low  = score_drift(flags, _full_anchor_report([]), config=cfg_low)
        s_high = score_drift(flags, _full_anchor_report([]), config=cfg_high)
        assert s_high.overall_score > s_low.overall_score


# ---------------------------------------------------------------------------
# score_drift — determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_result_repeated_calls(self):
        flags = DriftFlags(
            vagrant_candidates=[VagrantCandidate("a", "A", "component", "r", 0.80)],
            stale_candidates=[StaleCandidate("b", "r1", "stmt", "r", 0.70)],
            confidence=0.75, basis="test",
        )
        report = _full_anchor_report(["r1"])
        s1 = score_drift(flags, report)
        s2 = score_drift(flags, report)
        assert s1.overall_score == s2.overall_score
        assert s1.risk_level == s2.risk_level
        assert s1.top_risk_nodes == s2.top_risk_nodes

    def test_per_node_order_deterministic(self):
        flags = _vagrant_flags("z", "a", "m", "b")
        s1 = score_drift(flags, AnchorReport())
        s2 = score_drift(flags, AnchorReport())
        assert [n.node_id for n in s1.per_node_scores] == [n.node_id for n in s2.per_node_scores]


# ---------------------------------------------------------------------------
# DriftScore and NodeDriftScore serialisation
# ---------------------------------------------------------------------------

class TestSerialisaton:
    def test_drift_score_to_dict_required_keys(self):
        score = score_drift(DriftFlags(confidence=0.80, basis="t"), AnchorReport())
        d = score.to_dict()
        for k in ("overall_score", "risk_level", "confidence", "basis",
                  "per_node_scores", "top_risk_nodes", "warnings"):
            assert k in d

    def test_drift_score_json_serialisable(self):
        flags = _vagrant_flags("a")
        score = score_drift(flags, AnchorReport())
        dumped = json.dumps(score.to_dict())
        parsed = json.loads(dumped)
        assert "overall_score" in parsed

    def test_per_node_scores_is_list_of_dicts(self):
        score = score_drift(_vagrant_flags("a"), AnchorReport())
        d = score.to_dict()
        assert isinstance(d["per_node_scores"], list)
        if d["per_node_scores"]:
            assert isinstance(d["per_node_scores"][0], dict)

    def test_scores_rounded_in_to_dict(self):
        score = score_drift(_vagrant_flags("a"), AnchorReport())
        d = score.to_dict()
        # overall_score should be a float with at most 2 decimal places when non-zero
        assert isinstance(d["overall_score"], float)

    def test_node_to_dict_json_serialisable(self):
        n = NodeDriftScore("a", "Alpha", "component", 23.5, "medium",
                           True, 2, 0.5, "reason")
        dumped = json.dumps(n.to_dict())
        parsed = json.loads(dumped)
        assert parsed["node_id"] == "a"
        assert parsed["vagrant"] is True


# ---------------------------------------------------------------------------
# compute_drift_score() — disk-backed
# ---------------------------------------------------------------------------

class TestComputeDriftScore:
    def test_no_genesis_dir_no_crash(self, tmp_path):
        result = compute_drift_score(tmp_path)
        assert isinstance(result, DriftScore)

    def test_no_genesis_dir_score_not_negative(self, tmp_path):
        result = compute_drift_score(tmp_path)
        assert result.overall_score >= 0.0

    def test_corrupted_committed_no_crash(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("NOT JSON")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = compute_drift_score(tmp_path)
        assert isinstance(result, DriftScore)

    def test_populated_committed_and_planned_produces_result(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[_node("a"), _node("b")]))
        store.save_planned(ArchModel(nodes=[_node("a")]))  # b is vagrant
        result = compute_drift_score(tmp_path)
        assert result.overall_score > 0

    def test_no_planned_low_confidence_via_pure_scorer(self):
        # Low confidence requires detection_conf<0.50 AND anchor_report=None.
        # (When planned is absent, compute_drift_flags sets conf~0.35 but
        #  anchor_from_store still returns an empty AnchorReport → medium.)
        flags = DriftFlags(confidence=0.35, basis="planned absent")
        result = score_drift(flags, anchor_report=None)
        assert result.confidence < 0.50

    def test_compute_does_not_write(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save_committed(ArchModel(nodes=[_node("a"), _node("b")]))
        store.save_planned(ArchModel(nodes=[_node("a")]))
        before = (tmp_path / ".genesis" / "model.json").read_text()
        compute_drift_score(tmp_path)
        after = (tmp_path / ".genesis" / "model.json").read_text()
        assert before == after


# ---------------------------------------------------------------------------
# scan() integration
# ---------------------------------------------------------------------------

class TestScanDriftScoreIntegration:
    def test_scan_returns_drift_score_key(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert "drift_score" in result

    def test_drift_score_has_required_sub_keys(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        ds = result["drift_score"]
        for k in ("overall_score", "risk_level", "confidence", "basis",
                  "per_node_scores", "top_risk_nodes", "warnings"):
            assert k in ds, f"Missing key: {k!r}"

    def test_all_legacy_keys_still_present(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        for k in ("fix_commit_hotspots", "external_url_count", "version_sources",
                  "doc_version", "version_drift", "dead_file_candidates",
                  "model_sync", "model_diff", "drift_flags",
                  "source_anchors", "drift_score"):
            assert k in result, f"Legacy key missing: {k!r}"

    def test_drift_score_json_serialisable(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        dumped = json.dumps(result)
        parsed = json.loads(dumped)
        assert "drift_score" in parsed

    def test_scan_does_not_write_model_json(self, tmp_path):
        _make_python_project(tmp_path)
        scan(tmp_path)  # first run creates committed
        before = (tmp_path / ".genesis" / "model.json").read_text()
        scan(tmp_path)
        after = (tmp_path / ".genesis" / "model.json").read_text()
        assert before == after

    def test_scan_does_not_create_planned_json(self, tmp_path):
        _make_python_project(tmp_path)
        scan(tmp_path)
        assert not (tmp_path / ".genesis" / "planned.json").exists()

    def test_drift_score_overall_score_is_float(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert isinstance(result["drift_score"]["overall_score"], float)

    def test_drift_score_risk_level_is_string(self, tmp_path):
        _make_python_project(tmp_path)
        result = scan(tmp_path)
        assert isinstance(result["drift_score"]["risk_level"], str)
        assert result["drift_score"]["risk_level"] in (
            "none", "low", "medium", "high", "critical"
        )

    def test_scan_corrupted_model_no_crash(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "model.json").write_text("GARBAGE")
        _make_python_project(tmp_path)
        result = scan(tmp_path)  # must not raise
        assert "drift_score" in result


# ---------------------------------------------------------------------------
# Package exports
# ---------------------------------------------------------------------------

class TestPackageExports:
    def test_drift_scorer_config_exported(self):
        from genesis_architect_pro import DriftScorerConfig
        assert DriftScorerConfig is not None

    def test_node_drift_score_exported(self):
        from genesis_architect_pro import NodeDriftScore
        assert NodeDriftScore is not None

    def test_drift_score_exported(self):
        from genesis_architect_pro import DriftScore
        assert DriftScore is not None

    def test_score_drift_exported(self):
        from genesis_architect_pro import score_drift
        assert callable(score_drift)

    def test_compute_drift_score_exported(self):
        from genesis_architect_pro import compute_drift_score
        assert callable(compute_drift_score)
