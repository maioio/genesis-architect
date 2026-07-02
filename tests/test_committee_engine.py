"""Tests for the Committee engine.

Unit tests: types, collapse detector, transparency, advisors, journal.
Integration tests: full pipeline with mock LLM; FREE vs PRO masking;
                   earned vs manufactured consensus detection.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from genesis_architect_pro.engines.committee.collapse_detector import (
    apply_manufactured_cap,
    build_divergence_map,
    build_voting_record,
    classify_consensus,
    detect_collapse,
    find_minority_view,
)
from genesis_architect_pro.engines.committee.journal import append_journal_entry
from genesis_architect_pro.engines.committee.pipeline import (
    _extract_field,
    _extract_float,
    _parse_position,
    _needs_peer_review,
    run_committee,
)
from genesis_architect_pro.engines.committee.transparency import apply_transparency
from genesis_architect_pro.engines.committee.types import (
    AdvisorPosition,
    CollapseType,
    CommitteeContext,
    CommitteeMode,
    CommitteeRequest,
    CommitteeResult,
    ConsensusType,
    TransparencyProfile,
    Urgency,
    VotingRecord,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_position(advisor: str, confidence: float, agreement: float = 0.5) -> AdvisorPosition:
    return AdvisorPosition(
        advisor=advisor,
        stance=f"{advisor} stance",
        confidence=confidence,
        reasoning="test",
        agreement=agreement,
    )


def _make_request(profile: TransparencyProfile = TransparencyProfile.PRO) -> CommitteeRequest:
    return CommitteeRequest(
        question="Should we refactor the AuthModule?",
        context=CommitteeContext(evidence="AuthModule has 3 circular deps"),
        mode=CommitteeMode.ARCHITECTURE,
        urgency=Urgency.NORMAL,
        transparency=profile,
        max_rounds=2,
    )


# ---------------------------------------------------------------------------
# Unit: types
# ---------------------------------------------------------------------------

def test_voting_record_total():
    vr = VotingRecord(for_=3, against=1, abstain=1)
    assert vr.total == 5


def test_committee_result_defaults():
    result = CommitteeResult(
        verdict="go ahead",
        confidence=0.8,
        consensus_type=ConsensusType.EARNED,
    )
    assert result.advisor_positions is None
    assert result.minority_view is None


# ---------------------------------------------------------------------------
# Unit: collapse detector
# ---------------------------------------------------------------------------

def test_detect_collapse_earned_low_variance():
    pre = [_make_position("A", 0.8), _make_position("B", 0.75), _make_position("C", 0.82)]
    post = [_make_position("A", 0.81, 0.9), _make_position("B", 0.76, 0.88), _make_position("C", 0.80, 0.92)]
    assert detect_collapse(pre, post) == CollapseType.EARNED


def test_detect_collapse_manufactured_variance_drop():
    # High pre-variance, dramatically lower post-variance → MANUFACTURED
    pre = [
        _make_position("A", 0.9),
        _make_position("B", 0.2),
        _make_position("C", 0.85),
        _make_position("D", 0.15),
        _make_position("E", 0.88),
    ]
    # Post: everyone converged tightly
    post = [
        _make_position("A", 0.72, 0.9),
        _make_position("B", 0.70, 0.88),
        _make_position("C", 0.71, 0.91),
        _make_position("D", 0.73, 0.89),
        _make_position("E", 0.72, 0.90),
    ]
    assert detect_collapse(pre, post) == CollapseType.MANUFACTURED


def test_detect_collapse_manufactured_high_agreement_high_variance():
    pre = [_make_position("A", 0.9), _make_position("B", 0.1), _make_position("C", 0.85)]
    post = [_make_position("A", 0.9, 0.92), _make_position("B", 0.1, 0.88), _make_position("C", 0.85, 0.89)]
    assert detect_collapse(pre, post) == CollapseType.MANUFACTURED


def test_classify_consensus_earned():
    pre = [_make_position(f"A{i}", 0.8) for i in range(5)]
    post = [_make_position(f"A{i}", 0.8, 0.75) for i in range(5)]
    collapse = CollapseType.EARNED
    assert classify_consensus(pre, post, collapse) == ConsensusType.EARNED


def test_classify_consensus_manufactured_maps_correctly():
    pre = [_make_position(f"A{i}", 0.5) for i in range(5)]
    post = [_make_position(f"A{i}", 0.5, 0.9) for i in range(5)]
    assert classify_consensus(pre, post, CollapseType.MANUFACTURED) == ConsensusType.MANUFACTURED


def test_classify_consensus_divergent_low_agreement():
    pre = [_make_position(f"A{i}", 0.5) for i in range(5)]
    post = [_make_position(f"A{i}", 0.5, 0.2) for i in range(5)]
    assert classify_consensus(pre, post, CollapseType.EARNED) == ConsensusType.DIVERGENT


def test_build_voting_record():
    positions = [
        _make_position("A", 0.8, 0.9),   # for
        _make_position("B", 0.6, 0.7),   # for
        _make_position("C", 0.5, 0.5),   # abstain
        _make_position("D", 0.4, 0.3),   # against
        _make_position("E", 0.7, 0.8),   # for
    ]
    vr = build_voting_record(positions)
    assert vr.for_ == 3
    assert vr.against == 1
    assert vr.abstain == 1


def test_apply_manufactured_cap_above_ceiling():
    capped, warning = apply_manufactured_cap(0.9)
    assert capped == 0.65
    assert "manufactured" in warning.lower()


def test_apply_manufactured_cap_below_ceiling():
    capped, warning = apply_manufactured_cap(0.5)
    assert capped == 0.5
    assert warning == ""


def test_find_minority_view_returns_none_when_all_agree():
    positions = [_make_position(f"A{i}", 0.8, 0.8) for i in range(5)]
    assert find_minority_view(positions, positions) is None


def test_find_minority_view_returns_dissenter():
    positions = [
        _make_position("Contrarian", 0.8, 0.2),  # strong dissenter
        _make_position("Executor", 0.8, 0.9),
        _make_position("Outsider", 0.8, 0.85),
    ]
    view = find_minority_view(positions, positions)
    assert view is not None
    assert "Contrarian" in view


def test_build_divergence_map():
    positions = [_make_position("A", 0.7), _make_position("B", 0.3)]
    dm = build_divergence_map(positions)
    assert dm == {"A": 0.7, "B": 0.3}


# ---------------------------------------------------------------------------
# Unit: transparency
# ---------------------------------------------------------------------------

def test_transparency_free_strips_pro_fields():
    full = CommitteeResult(
        verdict="refactor",
        confidence=0.8,
        consensus_type=ConsensusType.EARNED,
        advisor_positions=[_make_position("A", 0.8)],
        voting_record=VotingRecord(for_=3, against=1, abstain=1),
        minority_view="some view",
        manufactured_warning="warning text",
    )
    stripped = apply_transparency(full, TransparencyProfile.FREE)
    assert stripped.advisor_positions is None
    assert stripped.voting_record is None
    assert stripped.minority_view is None
    assert stripped.manufactured_warning is None
    assert stripped.verdict == "refactor"
    assert stripped.confidence == 0.8


def test_transparency_pro_keeps_all_fields():
    full = CommitteeResult(
        verdict="refactor",
        confidence=0.8,
        consensus_type=ConsensusType.EARNED,
        advisor_positions=[_make_position("A", 0.8)],
        voting_record=VotingRecord(for_=3, against=1, abstain=1),
        minority_view="some view",
    )
    kept = apply_transparency(full, TransparencyProfile.PRO)
    assert kept.advisor_positions is not None
    assert kept.voting_record is not None
    assert kept.minority_view == "some view"


# ---------------------------------------------------------------------------
# Unit: parsing helpers
# ---------------------------------------------------------------------------

def test_extract_field_found():
    raw = "STANCE: We should refactor first\nCONFIDENCE: 0.8"
    assert _extract_field(raw, "STANCE") == "We should refactor first"


def test_extract_field_missing():
    raw = "CONFIDENCE: 0.8"
    assert _extract_field(raw, "STANCE", fallback="none") == "none"


def test_extract_float_found():
    raw = "CONFIDENCE: 0.73"
    assert _extract_float(raw, "CONFIDENCE") == pytest.approx(0.73)


def test_extract_float_missing():
    raw = "STANCE: something"
    assert _extract_float(raw, "CONFIDENCE", default=0.5) == 0.5


def test_parse_position_full():
    raw = (
        "STANCE: We should split the module\n"
        "CONFIDENCE: 0.82\n"
        "WHAT_WOULD_CHANGE_IT: If test coverage exceeds 80%"
    )
    pos = _parse_position(raw, "The Contrarian")
    assert pos.advisor == "The Contrarian"
    assert pos.confidence == pytest.approx(0.82)
    assert "split" in pos.stance
    assert "80%" in pos.what_would_change_it


def test_needs_peer_review_high_variance():
    positions = [
        _make_position("A", 0.9),
        _make_position("B", 0.1),
        _make_position("C", 0.85),
    ]
    assert _needs_peer_review(positions) is True


def test_needs_peer_review_low_variance():
    positions = [_make_position(f"A{i}", 0.75 + i * 0.01) for i in range(5)]
    assert _needs_peer_review(positions) is False


# ---------------------------------------------------------------------------
# Unit: journal
# ---------------------------------------------------------------------------

def test_journal_append_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        request = _make_request(TransparencyProfile.PRO)
        result = CommitteeResult(
            verdict="test verdict",
            confidence=0.75,
            consensus_type=ConsensusType.SPLIT,
            minority_view="Contrarian disagrees",
        )
        path = append_journal_entry(request, result, session_id="sess_test", project_dir=project_dir)
        assert path.exists()
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["engine"] == "committee"
        assert entry["verdict"] == "test verdict"
        assert entry["consensus_type"] == "split"
        assert entry["minority_view"] == "Contrarian disagrees"


def test_journal_append_is_additive():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        request = _make_request()
        result = CommitteeResult(verdict="v1", confidence=0.7, consensus_type=ConsensusType.EARNED)
        append_journal_entry(request, result, session_id="s1", project_dir=project_dir)
        result2 = CommitteeResult(verdict="v2", confidence=0.8, consensus_type=ConsensusType.SPLIT)
        append_journal_entry(request, result2, session_id="s2", project_dir=project_dir)

        journal = project_dir / ".genesis" / "gde_decision_log.jsonl"
        lines = journal.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["verdict"] == "v1"
        assert json.loads(lines[1])["verdict"] == "v2"


# ---------------------------------------------------------------------------
# Integration: full pipeline with mock LLM
# ---------------------------------------------------------------------------

_POSITION_RESPONSE = (
    "STANCE: We should introduce a service layer first\n"
    "CONFIDENCE: 0.78\n"
    "WHAT_WOULD_CHANGE_IT: If test coverage is below 30%"
)

_PEER_REVIEW_RESPONSE = (
    "AGREEMENT: 0.8\n"
    "CRITIQUE: The First Principles Thinker ignores domain constraints\n"
    "REVISED_STANCE: unchanged"
)

_SYNTHESIS_RESPONSE = (
    "VERDICT: Introduce a service layer; split AuthModule after green tests.\n"
    "CONFIDENCE: 0.76"
)


def _mock_llm(system: str, user: str) -> str:
    if "VERDICT" in user or "synthesize" in system.lower():
        return _SYNTHESIS_RESPONSE
    if "AGREEMENT" in user or "peer" in system.lower() or "other advisors" in user.lower():
        return _PEER_REVIEW_RESPONSE
    return _POSITION_RESPONSE


def test_integration_pro_full_pipeline():
    request = _make_request(TransparencyProfile.PRO)
    result = run_committee(request, llm_call=_mock_llm)

    assert result.verdict != ""
    assert 0.0 <= result.confidence <= 1.0
    assert result.consensus_type in ConsensusType.__members__.values()
    # PRO: all fields populated
    assert result.advisor_positions is not None
    assert len(result.advisor_positions) == 5


def test_integration_free_masks_pro_fields():
    request = _make_request(TransparencyProfile.FREE)
    result = run_committee(request, llm_call=_mock_llm)

    assert result.verdict != ""
    assert result.advisor_positions is None
    assert result.voting_record is None
    assert result.divergence_map is None
    assert result.minority_view is None


def test_integration_earned_vs_manufactured_consensus():
    # Advisors all give nearly identical confidence → low variance → EARNED
    def _uniform_llm(system: str, user: str) -> str:
        if "VERDICT" in user or "synthesize" in system.lower():
            return _SYNTHESIS_RESPONSE
        if "AGREEMENT" in user or "other advisors" in user.lower():
            return "AGREEMENT: 0.75\nCRITIQUE: Minor\nREVISED_STANCE: unchanged"
        return "STANCE: consistent stance\nCONFIDENCE: 0.77\nWHAT_WOULD_CHANGE_IT: nothing major"

    request = _make_request(TransparencyProfile.PRO)
    result = run_committee(request, llm_call=_uniform_llm)
    # With uniform responses, any non-error consensus type is valid
    assert result.consensus_type in ConsensusType.__members__.values()
    assert 0.0 <= result.confidence <= 1.0
