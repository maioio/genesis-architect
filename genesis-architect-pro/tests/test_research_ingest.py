"""Tests for research_ingest, the field_intelligence adapter's use of it, and the
RESEARCH_EVIDENCE_UNKNOWN gate.

Together they cover one guarantee: findings gathered outside Genesis can reach
the RESEARCH engines, and a research session with nothing to evaluate reports
UNKNOWN instead of passing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from genesis_architect_pro.engine_registry import EngineRegistry
from genesis_architect_pro.gde_engine_adapters import (
    gde_run_evidence_pack,
    gde_run_field_intelligence,
)
from genesis_architect_pro.gde_gate_engine import evaluate_gates
from genesis_architect_pro.gde_planner import build_plan
from genesis_architect_pro.gde_types import (
    EngineResult,
    EngineStatus,
    GateAction,
    GDEMode,
    Intent,
    SessionContext,
)
from genesis_architect_pro.research_ingest import (
    MAX_FINDINGS,
    findings_path,
    ingest_file,
    load_ingested,
)
from genesis_architect_pro.research_outline import Outline, save_outline

GATE = "RESEARCH_EVIDENCE_UNKNOWN"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, payload, name: str = "findings.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _finding(claim: str = "pgvector recall drops past 2M rows", **extra) -> dict:
    return {"claim": claim, "source_id": "reddit_answers", **extra}


def _ctx(project: Path, instruction: str = "research vector databases") -> SessionContext:
    ctx = SessionContext(mode=GDEMode.RESEARCH, project_dir=project)
    ctx.intent = Intent(raw_text=instruction, mode=GDEMode.RESEARCH, confidence=0.9)
    return ctx


def _fired(report) -> dict:
    return {r.gate_id: r for r in [*report.hard_blocks, *report.blocks, *report.warnings]}


# ---------------------------------------------------------------------------
# ingest_file: validation
# ---------------------------------------------------------------------------


class TestIngestValidation:
    def test_valid_file_is_stored(self, tmp_path):
        src = _write(tmp_path, {"findings": [_finding()]})
        result = ingest_file(src, tmp_path)
        assert result.ok
        assert result.accepted == 1 and result.total_stored == 1
        assert findings_path(tmp_path).is_file()

    def test_bare_list_is_accepted(self, tmp_path):
        result = ingest_file(_write(tmp_path, [_finding()]), tmp_path)
        assert result.ok and result.accepted == 1

    def test_claim_is_required(self, tmp_path):
        src = _write(tmp_path, {"findings": [{"source_id": "reddit_answers"}, _finding()]})
        result = ingest_file(src, tmp_path)
        assert result.ok
        assert result.accepted == 1
        assert len(result.rejected) == 1 and "claim" in result.rejected[0]

    def test_nothing_usable_is_an_error_and_writes_nothing(self, tmp_path):
        result = ingest_file(_write(tmp_path, {"findings": [{"claim": "  "}]}), tmp_path)
        assert not result.ok and "nothing usable" in result.error
        assert not findings_path(tmp_path).exists()

    def test_missing_file(self, tmp_path):
        result = ingest_file(tmp_path / "nope.json", tmp_path)
        assert not result.ok and "not found" in result.error

    def test_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        result = ingest_file(bad, tmp_path)
        assert not result.ok and "not valid JSON" in result.error

    def test_unknown_source_id_is_kept_with_a_warning(self, tmp_path):
        src = _write(tmp_path, {"findings": [_finding(source_id="made_up_source")]})
        result = ingest_file(src, tmp_path)
        assert result.ok and result.accepted == 1
        assert any("not in the source registry" in w for w in result.warnings)

    def test_findings_are_capped(self, tmp_path):
        many = [_finding(claim=f"claim {i}") for i in range(MAX_FINDINGS + 25)]
        result = ingest_file(_write(tmp_path, many), tmp_path)
        assert result.ok and result.total_stored == MAX_FINDINGS
        assert any("only the first" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Verification is derived from evidence, never taken from the file (G-6)
# ---------------------------------------------------------------------------


class TestVerificationIsDerived:
    def test_self_declared_verified_is_ignored(self, tmp_path):
        src = _write(tmp_path, {"findings": [_finding(verified=True)]})
        result = ingest_file(src, tmp_path)
        assert result.verified == 0 and result.unverified == 1
        assert any("'verified' in the file is ignored" in w for w in result.warnings)
        assert load_ingested(tmp_path).findings[0].verified is False

    def test_official_source_confirmation_verifies(self, tmp_path):
        src = _write(tmp_path, {"findings": [_finding(confirmed_by=["official_docs"])]})
        result = ingest_file(src, tmp_path)
        assert result.verified == 1
        finding = load_ingested(tmp_path).findings[0]
        assert finding.verified and finding.verified_by == ["official_docs"]

    def test_non_truth_source_does_not_verify(self, tmp_path):
        src = _write(tmp_path, {"findings": [_finding(confirmed_by=["reddit"])]})
        assert ingest_file(src, tmp_path).verified == 0

    def test_contradiction_beats_confirmation(self, tmp_path):
        src = _write(tmp_path, {"findings": [
            _finding(confirmed_by=["official_docs"], contradicted_by=["github_issues"])]})
        result = ingest_file(src, tmp_path)
        assert result.contradicted == 1 and result.verified == 0

    def test_store_never_holds_a_verified_flag(self, tmp_path):
        src = _write(tmp_path, {"findings": [_finding(verified=True, confirmed_by=["official_docs"])]})
        ingest_file(src, tmp_path)
        stored = json.loads(findings_path(tmp_path).read_text(encoding="utf-8"))
        for rec in stored["findings"]:
            assert "verified" not in rec
        assert "verified" not in json.dumps(stored)

    def test_editing_the_evidence_changes_the_verdict(self, tmp_path):
        """Verification is re-derived on every read, so the stored evidence is
        the single source of truth."""
        ingest_file(_write(tmp_path, {"findings": [_finding(confirmed_by=["official_docs"])]}), tmp_path)
        assert load_ingested(tmp_path).findings[0].verified

        store = json.loads(findings_path(tmp_path).read_text(encoding="utf-8"))
        store["findings"][0]["confirmed_by"] = []
        findings_path(tmp_path).write_text(json.dumps(store), encoding="utf-8")
        assert load_ingested(tmp_path).findings[0].verified is False

    def test_store_has_no_machine_specific_paths(self, tmp_path):
        ingest_file(_write(tmp_path, {"findings": [_finding()]}), tmp_path)
        text = findings_path(tmp_path).read_text(encoding="utf-8")
        assert str(tmp_path) not in text


# ---------------------------------------------------------------------------
# ingest_file: storage behaviour
# ---------------------------------------------------------------------------


class TestIngestStorage:
    def test_merge_deduplicates(self, tmp_path):
        first = _write(tmp_path, {"findings": [_finding("a"), _finding("b")]}, "one.json")
        second = _write(tmp_path, {"findings": [_finding("b"), _finding("c")]}, "two.json")
        ingest_file(first, tmp_path)
        result = ingest_file(second, tmp_path)
        assert result.accepted == 1 and result.total_stored == 3

    def test_replace_starts_over(self, tmp_path):
        ingest_file(_write(tmp_path, {"findings": [_finding("a"), _finding("b")]}, "one.json"), tmp_path)
        result = ingest_file(_write(tmp_path, {"findings": [_finding("c")]}, "two.json"),
                             tmp_path, replace=True)
        assert result.total_stored == 1

    def test_dry_run_writes_nothing(self, tmp_path):
        result = ingest_file(_write(tmp_path, {"findings": [_finding()]}), tmp_path, dry_run=True)
        assert result.ok and result.dry_run and result.accepted == 1
        assert not findings_path(tmp_path).exists()

    def test_grid_and_uncertain_are_stored(self, tmp_path):
        src = _write(tmp_path, {
            "item_findings": {"qdrant": {"license": "Apache-2.0", "ops": "  "}},
            "uncertain": ["qdrant:license"],
        })
        result = ingest_file(src, tmp_path)
        assert result.ok and result.grid_cells == 1
        loaded = load_ingested(tmp_path)
        assert loaded.item_findings == {"qdrant": {"license": "Apache-2.0"}}
        assert loaded.uncertain == ["qdrant:license"]

    def test_unreadable_existing_store_is_not_silently_overwritten(self, tmp_path):
        findings_path(tmp_path).parent.mkdir(parents=True)
        findings_path(tmp_path).write_text("{corrupt", encoding="utf-8")
        result = ingest_file(_write(tmp_path, {"findings": [_finding()]}), tmp_path)
        assert not result.ok and "--replace" in result.error
        assert findings_path(tmp_path).read_text(encoding="utf-8") == "{corrupt"
        assert ingest_file(_write(tmp_path, {"findings": [_finding()]}), tmp_path, replace=True).ok

    def test_load_fails_closed_on_a_corrupt_store(self, tmp_path):
        findings_path(tmp_path).parent.mkdir(parents=True)
        findings_path(tmp_path).write_text("{corrupt", encoding="utf-8")
        loaded = load_ingested(tmp_path)
        assert loaded.present and loaded.error and loaded.findings == []

    def test_absent_store_is_not_an_error(self, tmp_path):
        loaded = load_ingested(tmp_path)
        assert not loaded.present and not loaded.error and loaded.findings == []


# ---------------------------------------------------------------------------
# field_intelligence adapter
# ---------------------------------------------------------------------------


class TestFieldIntelligenceAdapter:
    def test_empty_session_warns_honestly(self, tmp_path):
        out = gde_run_field_intelligence(_ctx(tmp_path))
        assert out["findings"] == [] and out["coverage"] is None
        text = " ".join(out["_warnings"])
        assert "genesis ingest" in text
        assert "network" not in text  # the old warning blamed the network

    def test_ingested_findings_reach_the_engine(self, tmp_path):
        ingest_file(_write(tmp_path, {"findings": [
            _finding("a", confirmed_by=["official_docs"]), _finding("b")]}), tmp_path)
        out = gde_run_field_intelligence(_ctx(tmp_path))
        assert len(out["findings"]) == 2 and out["verified_count"] == 1
        assert out["_confidence"] == 0.8
        assert not any("genesis ingest" in w for w in out["_warnings"])

    def test_no_outline_means_no_coverage(self, tmp_path):
        ingest_file(_write(tmp_path, {"findings": [_finding()]}), tmp_path)
        assert gde_run_field_intelligence(_ctx(tmp_path))["coverage"] is None

    def test_coverage_is_measured_against_the_outline(self, tmp_path):
        save_outline(Outline(topic="vector dbs", items=["qdrant", "milvus"],
                             fields=["license", "ops"]), tmp_path)
        ingest_file(_write(tmp_path, {"item_findings": {
            "qdrant": {"license": "Apache-2.0", "ops": "low"}}}), tmp_path)
        out = gde_run_field_intelligence(_ctx(tmp_path))
        assert out["coverage"] == pytest.approx(0.5)
        assert out["outline"] == {"topic": "vector dbs"}

    def test_outline_with_nothing_ingested_is_measured_zero(self, tmp_path):
        save_outline(Outline(topic="vector dbs", items=["qdrant"], fields=["license"]), tmp_path)
        assert gde_run_field_intelligence(_ctx(tmp_path))["coverage"] == 0.0

    def test_corrupt_store_is_surfaced_and_counts_as_no_evidence(self, tmp_path):
        findings_path(tmp_path).parent.mkdir(parents=True)
        findings_path(tmp_path).write_text("{corrupt", encoding="utf-8")
        out = gde_run_field_intelligence(_ctx(tmp_path))
        assert out["findings"] == []
        assert any("unreadable" in w for w in out["_warnings"])


class TestEvidencePackAdapter:
    def _pack(self, project: Path) -> dict:
        ctx = _ctx(project)
        ctx.engine_results["field_intelligence"] = EngineResult(
            engine_id="field_intelligence", status=EngineStatus.SUCCESS,
            output=gde_run_field_intelligence(ctx))
        out = gde_run_evidence_pack(ctx)
        return json.loads(out["_pending_writes"][0]["payload"])

    def test_unverified_signal_alone_never_grades_above_low(self, tmp_path):
        ingest_file(_write(tmp_path, {"findings": [_finding()]}), tmp_path)
        pack = self._pack(tmp_path)
        assert pack["confidence"] == "low"
        assert pack["items"][0]["status"] == "unverified"

    def test_confirming_source_is_graded_on_its_own_tier(self, tmp_path):
        ingest_file(_write(tmp_path, {"findings": [
            _finding(confirmed_by=["official_docs", "github_issues"])]}), tmp_path)
        pack = self._pack(tmp_path)
        assert pack["confidence"] in ("medium", "high")
        assert {i["source_id"] for i in pack["items"]} >= {"official_docs", "github_issues"}

    def test_contradiction_is_surfaced(self, tmp_path):
        ingest_file(_write(tmp_path, {"findings": [
            _finding("x is safe", contradicted_by=["osv"])]}), tmp_path)
        pack = self._pack(tmp_path)
        assert any("x is safe" in c and "osv" in c for c in pack["contradictions"])


# ---------------------------------------------------------------------------
# RESEARCH_EVIDENCE_UNKNOWN gate (G-7: cannot evaluate -> UNKNOWN, not PASS)
# ---------------------------------------------------------------------------


def _result(ctx: SessionContext, engine_id: str, output: dict) -> None:
    ctx.engine_results[engine_id] = EngineResult(
        engine_id=engine_id, status=EngineStatus.SUCCESS, output=output)


class TestEvidenceUnknownGate:
    def test_fires_when_the_session_has_no_evidence(self):
        ctx = SessionContext(mode=GDEMode.RESEARCH)
        _result(ctx, "field_intelligence", {"findings": [], "coverage": None})
        fired = _fired(evaluate_gates(ctx, [GATE]))
        assert GATE in fired
        assert "UNKNOWN" in fired[GATE].reason
        assert "genesis ingest" in fired[GATE].detail

    def test_fires_when_the_engine_never_ran(self):
        """No inputs at all is the same inability to evaluate, not a pass."""
        assert GATE in _fired(evaluate_gates(SessionContext(mode=GDEMode.RESEARCH), [GATE]))

    def test_is_a_visible_overridable_warning_never_a_pass(self):
        ctx = SessionContext(mode=GDEMode.RESEARCH)
        _result(ctx, "field_intelligence", {"findings": [], "coverage": None})
        report = evaluate_gates(ctx, [GATE])
        assert report.overall.name == "WARN"
        assert report.warnings and not report.passed
        assert report.warnings[0].action == GateAction.WARN
        assert report.warnings[0].override_allowed is True

    def test_silent_when_findings_exist(self):
        ctx = SessionContext(mode=GDEMode.RESEARCH)
        _result(ctx, "field_intelligence", {"findings": [object()], "coverage": None})
        assert GATE not in _fired(evaluate_gates(ctx, [GATE]))

    def test_silent_when_coverage_was_measured_even_at_zero(self):
        """0.0 is a measured value; RESEARCH_COVERAGE_LOW speaks for it."""
        ctx = SessionContext(mode=GDEMode.RESEARCH)
        _result(ctx, "field_intelligence", {"findings": [], "coverage": 0.0})
        report = evaluate_gates(ctx, [GATE, "RESEARCH_COVERAGE_LOW"])
        fired = _fired(report)
        assert GATE not in fired and "RESEARCH_COVERAGE_LOW" in fired

    def test_another_engines_findings_do_not_count_as_research_evidence(self):
        """red_team_critic also emits `findings`; those are not research."""
        ctx = SessionContext(mode=GDEMode.RESEARCH)
        _result(ctx, "red_team_critic", {"findings": [{"severity": "low"}]})
        assert GATE in _fired(evaluate_gates(ctx, [GATE]))

    def test_coverage_none_still_does_not_fire_the_coverage_gate(self):
        """The existing contract is untouched: None coverage is 'not applicable'."""
        ctx = SessionContext(mode=GDEMode.RESEARCH)
        _result(ctx, "field_intelligence", {"findings": [], "coverage": None})
        assert "RESEARCH_COVERAGE_LOW" not in _fired(evaluate_gates(ctx, ["RESEARCH_COVERAGE_LOW"]))

    def test_research_mode_requires_the_gate(self):
        intent = Intent(raw_text="test", mode=GDEMode.RESEARCH, confidence=0.9)
        plan = build_plan(intent, registry=EngineRegistry())
        assert GATE in plan.required_gate_ids
        assert "RESEARCH_COVERAGE_LOW" in plan.required_gate_ids

    def test_end_to_end_empty_then_ingested(self, tmp_path):
        """The full loop: an empty session is UNKNOWN; after `ingest` it is not."""
        empty = _ctx(tmp_path)
        _result(empty, "field_intelligence", gde_run_field_intelligence(empty))
        assert GATE in _fired(evaluate_gates(empty, [GATE]))

        ingest_file(_write(tmp_path, {"findings": [_finding(confirmed_by=["official_docs"])]}), tmp_path)
        fed = _ctx(tmp_path)
        _result(fed, "field_intelligence", gde_run_field_intelligence(fed))
        assert GATE not in _fired(evaluate_gates(fed, [GATE]))


# ---------------------------------------------------------------------------
# CLI: `genesis ingest`
# ---------------------------------------------------------------------------


class TestIngestCommand:
    def test_command_is_reachable_and_writes(self, tmp_path, capsys):
        from genesis_architect_pro.cli.router import main

        src = _write(tmp_path, {"findings": [_finding(confirmed_by=["official_docs"])]})
        rc = main(["ingest", str(src), "--dir", str(tmp_path), "--json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] and payload["verified"] == 1
        assert findings_path(tmp_path).is_file()

    def test_dry_run_flag(self, tmp_path, capsys):
        from genesis_architect_pro.cli.router import main

        src = _write(tmp_path, {"findings": [_finding()]})
        assert main(["ingest", str(src), "--dir", str(tmp_path), "--dry-run", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["dry_run"] is True
        assert not findings_path(tmp_path).exists()

    def test_bad_file_returns_nonzero(self, tmp_path, capsys):
        from genesis_architect_pro.cli.router import main

        rc = main(["ingest", str(tmp_path / "missing.json"), "--dir", str(tmp_path)])
        assert rc == 1
        assert "not found" in capsys.readouterr().out

    def test_bad_directory_returns_nonzero(self, tmp_path):
        from genesis_architect_pro.cli.router import main

        src = _write(tmp_path, {"findings": [_finding()]})
        assert main(["ingest", str(src), "--dir", str(tmp_path / "nope")]) == 1
