"""Tests for red_team_critic.py — the self-critique engine that attacks a
session's own plan before it's approved."""

from __future__ import annotations

import pytest

from genesis_architect_pro.gde_types import (
    EngineResult,
    EngineStatus,
    GDEMode,
    SessionContext,
    WriteOperation,
)
from genesis_architect_pro.red_team_critic import (
    RedTeamFinding,
    _build_attack_prompt,
    _parse_llm_findings,
    critique_session,
    critique_with_llm,
    run_red_team,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(**kwargs) -> SessionContext:
    return SessionContext(**kwargs)


def _write_op(engine_id, operation_id, target_path, is_reversible=True):
    return WriteOperation(
        engine_id=engine_id,
        operation_id=operation_id,
        description="test write",
        target_path=target_path,
        is_reversible=is_reversible,
    )


def _result(engine_id, status=EngineStatus.SUCCESS, confidence=1.0):
    return EngineResult(engine_id=engine_id, status=status, confidence=confidence)


# ---------------------------------------------------------------------------
# Conflicting writes
# ---------------------------------------------------------------------------


class TestConflictingWrites:
    def test_no_writes_no_findings(self):
        # isolate from the unfounded_confidence check (default overall_confidence
        # is 1.0 with zero engine results, which correctly fires on its own —
        # covered separately in TestUnfoundedConfidence).
        ctx = _ctx()
        ctx.overall_confidence = 0.5
        assert critique_session(ctx) == []

    def test_single_write_no_conflict(self):
        ctx = _ctx()
        ctx.pending_write_operations.append(_write_op("engine_a", "op1", "a.md"))
        findings = critique_session(ctx)
        assert not any(f.category == "conflicting_writes" for f in findings)

    def test_two_engines_same_path_flagged_critical(self):
        ctx = _ctx()
        ctx.pending_write_operations.append(_write_op("engine_a", "op1", "shared.md"))
        ctx.pending_write_operations.append(_write_op("engine_b", "op2", "shared.md"))
        findings = critique_session(ctx)
        conflict = [f for f in findings if f.category == "conflicting_writes"]
        assert len(conflict) == 1
        assert conflict[0].severity == "critical"

    def test_same_engine_same_path_not_flagged(self):
        # one engine writing to the same path twice is its own business, not a conflict
        ctx = _ctx()
        ctx.pending_write_operations.append(_write_op("engine_a", "op1", "a.md"))
        ctx.pending_write_operations.append(_write_op("engine_a", "op2", "a.md"))
        findings = critique_session(ctx)
        assert not any(f.category == "conflicting_writes" for f in findings)


# ---------------------------------------------------------------------------
# Irreversible + low confidence
# ---------------------------------------------------------------------------


class TestIrreversibleLowConfidence:
    def test_reversible_write_never_flagged(self):
        ctx = _ctx()
        ctx.pending_write_operations.append(_write_op("engine_a", "op1", "a.md", is_reversible=True))
        findings = critique_session(ctx)
        assert not any(f.category.startswith("irreversible") for f in findings)

    def test_irreversible_high_confidence_not_flagged(self):
        ctx = _ctx()
        ctx.pending_write_operations.append(_write_op("engine_a", "op1", "a.md", is_reversible=False))
        ctx.engine_results["engine_a"] = _result("engine_a", confidence=0.95)
        findings = critique_session(ctx)
        assert not any(f.category.startswith("irreversible") for f in findings)

    def test_irreversible_low_confidence_flagged_high(self):
        ctx = _ctx()
        ctx.pending_write_operations.append(_write_op("engine_a", "op1", "a.md", is_reversible=False))
        ctx.engine_results["engine_a"] = _result("engine_a", confidence=0.3)
        findings = critique_session(ctx)
        hits = [f for f in findings if f.category == "irreversible_low_confidence"]
        assert len(hits) == 1
        assert hits[0].severity == "high"

    def test_irreversible_no_result_flagged_critical(self):
        ctx = _ctx()
        ctx.pending_write_operations.append(_write_op("engine_a", "op1", "a.md", is_reversible=False))
        findings = critique_session(ctx)
        hits = [f for f in findings if f.category == "irreversible_no_evidence"]
        assert len(hits) == 1
        assert hits[0].severity == "critical"

    def test_irreversible_failed_engine_flagged(self):
        ctx = _ctx()
        ctx.pending_write_operations.append(_write_op("engine_a", "op1", "a.md", is_reversible=False))
        ctx.engine_results["engine_a"] = _result("engine_a", status=EngineStatus.FAILED, confidence=1.0)
        findings = critique_session(ctx)
        assert any(f.category == "irreversible_low_confidence" for f in findings)


# ---------------------------------------------------------------------------
# Unfounded confidence
# ---------------------------------------------------------------------------


class TestUnfoundedConfidence:
    def test_low_overall_confidence_not_flagged(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.5
        findings = critique_session(ctx)
        assert not any(f.category == "unfounded_confidence" for f in findings)

    def test_high_confidence_with_no_engine_results_flagged(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.9
        findings = critique_session(ctx)
        hits = [f for f in findings if f.category == "unfounded_confidence"]
        assert len(hits) == 1
        assert hits[0].severity == "critical"

    def test_high_confidence_with_only_failures_flagged(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.9
        ctx.engine_results["e1"] = _result("e1", status=EngineStatus.FAILED)
        findings = critique_session(ctx)
        assert any(f.category == "unfounded_confidence" for f in findings)

    def test_high_confidence_with_real_success_not_flagged(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.9
        ctx.engine_results["e1"] = _result("e1", status=EngineStatus.SUCCESS)
        findings = critique_session(ctx)
        assert not any(f.category == "unfounded_confidence" for f in findings)


# ---------------------------------------------------------------------------
# LLM adversarial pass — injected callable, no real API key needed
# ---------------------------------------------------------------------------


class TestLLMPass:
    def test_none_response_yields_no_findings(self):
        ctx = _ctx()
        result = critique_with_llm(ctx, llm_call=lambda s, u: "NONE")
        assert result == []

    def test_single_finding_parsed(self):
        ctx = _ctx()
        raw = (
            "FINDING: high\n"
            "CATEGORY: missing_step\n"
            "DESCRIPTION: The plan never validates the input before writing.\n"
            "---\n"
        )
        result = critique_with_llm(ctx, llm_call=lambda s, u: raw)
        assert len(result) == 1
        assert result[0].severity == "high"
        assert result[0].category == "missing_step"
        assert "validates" in result[0].description

    def test_multiple_findings_parsed(self):
        ctx = _ctx()
        raw = (
            "FINDING: critical\nCATEGORY: a\nDESCRIPTION: first issue\n---\n"
            "FINDING: low\nCATEGORY: b\nDESCRIPTION: second issue\n---\n"
        )
        result = critique_with_llm(ctx, llm_call=lambda s, u: raw)
        assert len(result) == 2
        assert {f.severity for f in result} == {"critical", "low"}

    def test_unknown_severity_defaults_to_medium(self):
        ctx = _ctx()
        raw = "FINDING: weird\nCATEGORY: x\nDESCRIPTION: something odd\n---\n"
        result = critique_with_llm(ctx, llm_call=lambda s, u: raw)
        assert result[0].severity == "medium"

    def test_llm_backend_failure_propagates(self):
        # critique_with_llm doesn't swallow errors itself — the adapter decides
        # how to disclose that, same as Committee's own _default_llm_call.
        ctx = _ctx()

        def boom(system, user):
            raise RuntimeError("no key")

        with pytest.raises(RuntimeError):
            critique_with_llm(ctx, llm_call=boom)

    def test_attack_prompt_includes_pending_writes_and_mode(self):
        ctx = _ctx(mode=GDEMode.RECOVERY)
        ctx.pending_write_operations.append(_write_op("engine_a", "op1", "a.md"))
        system, user = _build_attack_prompt(ctx)
        assert "recovery" in user
        assert "a.md" in user
        assert "engine_a" in user


# ---------------------------------------------------------------------------
# run_red_team — combined entry point
# ---------------------------------------------------------------------------


class TestRunRedTeam:
    def test_deterministic_only_by_default(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.9
        result = run_red_team(ctx)
        assert result["critical_count"] == 1  # unfounded_confidence
        assert result["finding_count"] == 1

    def test_use_llm_adds_findings(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.5  # isolate from the unfounded_confidence check
        raw = "FINDING: medium\nCATEGORY: x\nDESCRIPTION: extra\n---\n"
        result = run_red_team(ctx, use_llm=True, llm_call=lambda s, u: raw)
        assert result["finding_count"] == 1
        assert result["findings"][0]["category"] == "x"

    def test_output_shape_matches_engine_result_contract(self):
        ctx = _ctx()
        result = run_red_team(ctx)
        assert set(result.keys()) == {"findings", "critical_count", "finding_count"}
        assert isinstance(result["findings"], list)


# ---------------------------------------------------------------------------
# _parse_llm_findings edge cases
# ---------------------------------------------------------------------------


class TestEvidenceInferenceSeparation:
    """A4: evidence holds only what was observed; inference holds what follows.

    This module previously stated "Confidence in a conclusion drawn from no
    evidence is zero" in its evidence field — a claim about epistemics, not an
    observation. These tests keep that from coming back.
    """

    def test_finding_has_both_fields(self):
        f = RedTeamFinding(severity="low", category="x", description="d")
        assert f.evidence == "" and f.inference == ""

    def test_conflicting_writes_populates_both(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.5
        ctx.pending_write_operations.append(_write_op("a", "op1", "shared.md"))
        ctx.pending_write_operations.append(_write_op("b", "op2", "shared.md"))
        f = next(x for x in critique_session(ctx) if x.category == "conflicting_writes")
        assert f.evidence and f.inference
        assert "shared.md" in f.evidence and "engines=" in f.evidence

    def test_unfounded_confidence_evidence_is_measurements_only(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.9
        f = next(x for x in critique_session(ctx) if x.category == "unfounded_confidence")
        # Evidence must be readable values, not the argument about them.
        assert "overall_confidence=0.90" in f.evidence
        assert "engines_run=0" in f.evidence
        assert "zero" not in f.evidence.lower(), "the epistemic claim belongs in inference"
        assert "Confidence in a conclusion" in f.inference

    def test_irreversible_findings_populate_both(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.5
        ctx.pending_write_operations.append(
            _write_op("a", "op1", "x.md", is_reversible=False))
        ctx.engine_results["a"] = _result("a", confidence=0.2)
        f = next(x for x in critique_session(ctx)
                 if x.category == "irreversible_low_confidence")
        assert "is_reversible=False" in f.evidence and "confidence=0.20" in f.evidence
        assert f.inference

    def test_every_deterministic_finding_has_an_inference(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.9
        ctx.pending_write_operations.append(_write_op("a", "op1", "s.md"))
        ctx.pending_write_operations.append(_write_op("b", "op2", "s.md"))
        ctx.pending_write_operations.append(
            _write_op("c", "op3", "y.md", is_reversible=False))
        findings = critique_session(ctx)
        assert findings
        for f in findings:
            assert f.inference, f"{f.category} has no inference"
            assert f.evidence, f"{f.category} has no evidence"

    def test_llm_parses_evidence_and_inference_separately(self):
        raw = ("FINDING: high\nCATEGORY: c\nDESCRIPTION: d\n"
               "EVIDENCE: pending_writes=2\nINFERENCE: they collide\n---\n")
        f = _parse_llm_findings(raw)[0]
        assert f.evidence == "pending_writes=2"
        assert f.inference == "they collide"
        assert f.description == "d", "description must not swallow the later fields"

    def test_llm_missing_optional_fields_still_parses(self):
        f = _parse_llm_findings("FINDING: low\nCATEGORY: c\nDESCRIPTION: d\n---\n")[0]
        assert f.evidence == "" and f.inference == ""

    def test_run_red_team_exposes_inference(self):
        ctx = _ctx()
        ctx.overall_confidence = 0.9
        out = run_red_team(ctx)
        assert "inference" in out["findings"][0]


class TestParseLLMFindings:
    def test_empty_string(self):
        assert _parse_llm_findings("") == []

    def test_malformed_block_skipped(self):
        raw = "this is not a finding block at all\n---\n"
        assert _parse_llm_findings(raw) == []

    def test_finding_is_dataclass_instance(self):
        raw = "FINDING: low\nCATEGORY: x\nDESCRIPTION: y\n---\n"
        result = _parse_llm_findings(raw)
        assert isinstance(result[0], RedTeamFinding)
