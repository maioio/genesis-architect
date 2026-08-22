"""Tests for the supply-chain audit engine and the policy surface it feeds.

Covers the two dead gates this work revived — SECURITY_RISK, which nothing had
ever emitted, and RULES_FAIL, whose adapter never emitted the key the gate
reads — plus the shadow-mode contract that keeps the new default ruleset from
blocking anyone this release.
"""

import json

import pytest

from genesis_architect_pro import rules_engine
from genesis_architect_pro.gde_engine_adapters import (
    gde_run_rules_engine,
    gde_run_supply_chain_audit,
)
from genesis_architect_pro.gde_gate_engine import evaluate_gates
from genesis_architect_pro.gde_types import (
    EngineResult,
    EngineStatus,
    GateAction,
    GDEMode,
    SessionContext,
    WriteOperation,
)
from genesis_architect_pro.red_team_critic import _check_writes_unpinned_ci
from genesis_architect_pro.supply_chain_audit import (
    classify_ref,
    format_report,
    scan_workflows,
)

SHA = "11d5960a326750d5838078e36cf38b85af677262"

PINNED_WF = f"""name: release
jobs:
  build:
    steps:
      - uses: actions/checkout@{SHA} # v4
      - uses: ./local-action
"""

MIXED_WF = f"""name: ci
jobs:
  build:
    steps:
      - uses: actions/checkout@{SHA}
      - uses: actions/setup-node@v4
      - uses: some/action@main
      - uses: ./local-action
      # - uses: commented/out@v1
"""


def write_wf(root, name, content):
    wf = root / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / name).write_text(content, encoding="utf-8")


class TestClassifyRef:
    @pytest.mark.parametrize("raw,kind", [
        (f"actions/checkout@{SHA}", "sha"),
        (f"actions/checkout@{SHA} # v4", "sha"),
        (f"owner/repo/.github/workflows/x.yml@{SHA}", "sha"),
        ("actions/checkout@v4", "tag"),
        ("actions/checkout@4.1.0", "tag"),
        ("some/action@main", "branch"),
        ("some/action", "branch"),
        ("./local-action", "local"),
        ("../shared/action", "local"),
        ("docker://alpine@sha256:deadbeef", "digest"),
        ("docker://alpine:3.19", "unpinnable"),
    ])
    def test_kinds(self, raw, kind):
        assert classify_ref(raw)[2] == kind

    def test_abbreviated_sha_is_not_pinned(self):
        """A 12-char prefix resolves to whatever object starts with it."""
        assert classify_ref("actions/checkout@11d5960a3267")[2] != "sha"


class TestScanWorkflows:
    def test_no_ci_is_not_a_pass(self, tmp_path):
        report = scan_workflows(tmp_path)
        assert report.scanned is False
        assert report.unpinned == []
        assert "not a pass" in format_report(report)

    def test_all_pinned(self, tmp_path):
        write_wf(tmp_path, "release.yml", PINNED_WF)
        report = scan_workflows(tmp_path)
        assert report.scanned is True
        assert report.unpinned == []
        assert len(report.pinned) == 1

    def test_mixed_finds_only_the_mutable_ones(self, tmp_path):
        write_wf(tmp_path, "ci.yml", MIXED_WF)
        report = scan_workflows(tmp_path)
        refs = sorted(r.raw for r in report.unpinned)
        assert refs == ["actions/setup-node@v4", "some/action@main"]

    def test_commented_lines_are_not_scanned(self, tmp_path):
        write_wf(tmp_path, "ci.yml", MIXED_WF)
        report = scan_workflows(tmp_path)
        assert all("commented/out" not in r.raw for r in report.refs)

    def test_local_actions_are_exempt_not_pinned(self, tmp_path):
        write_wf(tmp_path, "ci.yml", MIXED_WF)
        report = scan_workflows(tmp_path)
        local = [r for r in report.refs if r.kind == "local"]
        assert local and local[0].is_exempt and not local[0].is_pinned

    def test_unpinnable_is_reported_separately_from_unpinned(self, tmp_path):
        write_wf(tmp_path, "ci.yml",
                 "jobs:\n  b:\n    steps:\n      - uses: docker://alpine:3.19\n")
        report = scan_workflows(tmp_path)
        assert len(report.unpinnable) == 1
        assert report.unpinned == []   # never counted as a failure

    def test_line_numbers_are_reported(self, tmp_path):
        write_wf(tmp_path, "ci.yml", MIXED_WF)
        report = scan_workflows(tmp_path)
        node = next(r for r in report.unpinned if "setup-node" in r.raw)
        assert node.line == 6 and node.file == ".github/workflows/ci.yml"


class TestAdapterAndSecurityRiskGate:
    """SECURITY_RISK scans every engine output for `security_risk`. Before this
    engine existed, nothing in the codebase ever set that key."""

    def _ctx(self, tmp_path):
        return SessionContext(mode=GDEMode.GATE, project_dir=tmp_path)

    def test_shadow_mode_reports_but_withholds_security_risk(self, tmp_path):
        write_wf(tmp_path, "ci.yml", MIXED_WF)
        out = gde_run_supply_chain_audit(self._ctx(tmp_path))
        assert out["policy_mode"] == "shadow"
        assert out["unpinned_count"] == 2
        assert "security_risk" not in out
        assert any("[shadow]" in w for w in out["_warnings"])

    def test_explicit_rules_file_makes_it_enforcing(self, tmp_path):
        write_wf(tmp_path, "ci.yml", MIXED_WF)
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "rules.json").write_text(json.dumps({"max_unpinned_actions": 0}),
                                            encoding="utf-8")
        out = gde_run_supply_chain_audit(self._ctx(tmp_path))
        assert out["policy_mode"] == "enforcing"
        assert out["security_risk"] is True
        assert "actions/setup-node@v4" in out["security_risk_detail"]

    def test_security_risk_gate_fires_on_the_output(self, tmp_path):
        """End-to-end: the emitted key reaches the existing gate untouched."""
        ctx = self._ctx(tmp_path)
        ctx.engine_results["supply_chain_audit"] = EngineResult(
            engine_id="supply_chain_audit", status=EngineStatus.SUCCESS,
            output={"security_risk": True, "security_risk_detail": "2 unpinned"},
        )
        report = evaluate_gates(ctx, ["SECURITY_RISK"])
        fired = [r for r in (*report.blocks, *report.warnings) if r.gate_id == "SECURITY_RISK"]
        assert fired and fired[0].action == GateAction.BLOCK_AND_ASK

    def test_no_ci_says_so_rather_than_reporting_clean(self, tmp_path):
        out = gde_run_supply_chain_audit(self._ctx(tmp_path))
        assert out["ci_scanned"] is False
        assert "security_risk" not in out
        assert any("unverified" in w for w in out["_warnings"])


class TestDefaultRulesetShadowMode:
    def test_no_rules_file_now_evaluates_the_default_ruleset(self, tmp_path):
        rules, path_used, source = rules_engine.load_rules(tmp_path)
        assert source == "default"
        assert path_used == ""
        assert rules == rules_engine.DEFAULT_RULES

    def test_policy_mode_reflects_provenance(self, tmp_path):
        assert rules_engine.policy_mode(tmp_path)[0] == "shadow"
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "rules.json").write_text("{}", encoding="utf-8")
        assert rules_engine.policy_mode(tmp_path) == ("enforcing", "file")

    def test_shadow_failures_are_not_hard_failures(self, tmp_path):
        write_wf(tmp_path, "ci.yml", MIXED_WF)
        report = rules_engine.run_check(tmp_path)
        assert report.shadow_mode is True
        assert report.passed is False          # the finding is real
        assert report.hard_failure is False    # and deliberately not escalated
        assert "SHADOW" in rules_engine.format_report(report)

    def test_explicit_rules_do_hard_fail(self, tmp_path):
        write_wf(tmp_path, "ci.yml", MIXED_WF)
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "rules.json").write_text(json.dumps({"max_unpinned_actions": 0}),
                                            encoding="utf-8")
        report = rules_engine.run_check(tmp_path)
        assert report.shadow_mode is False
        assert report.hard_failure is True
        assert "max_unpinned_actions" in report.hard_failure_reason

    def test_rule_is_skipped_not_passed_when_there_is_no_ci(self, tmp_path):
        genesis = tmp_path / ".genesis"
        genesis.mkdir()
        (genesis / "rules.json").write_text(json.dumps({"max_unpinned_actions": 0}),
                                            encoding="utf-8")
        report = rules_engine.run_check(tmp_path)
        assert not any(r.rule == "max_unpinned_actions" for r in report.results)
        assert any("skipped" in n for n in report.notes)

    def test_gather_facts_distinguishes_absent_ci_from_zero(self, tmp_path):
        assert rules_engine.gather_facts(tmp_path)["unpinned_actions"] is None
        write_wf(tmp_path, "ci.yml", PINNED_WF)
        assert rules_engine.gather_facts(tmp_path)["unpinned_actions"] == 0


class TestRulesFailGateIsNoLongerDead:
    """RULES_FAIL reads `hard_failure`. The adapter never emitted it, so the
    only non-overridable gate in the policy table had never fired."""

    def _ctx_with_rules(self, tmp_path, rules):
        genesis = tmp_path / ".genesis"
        genesis.mkdir(exist_ok=True)
        (genesis / "rules.json").write_text(json.dumps(rules), encoding="utf-8")
        ctx = SessionContext(mode=GDEMode.GATE, project_dir=tmp_path)
        out = gde_run_rules_engine(ctx)
        ctx.engine_results["rules_engine"] = EngineResult(
            engine_id="rules_engine", status=EngineStatus.SUCCESS, output=out)
        return ctx, out

    def test_adapter_emits_the_key_the_gate_reads(self, tmp_path):
        write_wf(tmp_path, "ci.yml", MIXED_WF)
        _ctx, out = self._ctx_with_rules(tmp_path, {"max_unpinned_actions": 0})
        assert out["hard_failure"] is True
        assert out["hard_failure_reason"]

    def test_gate_fires_and_is_not_overridable(self, tmp_path):
        write_wf(tmp_path, "ci.yml", MIXED_WF)
        ctx, _out = self._ctx_with_rules(tmp_path, {"max_unpinned_actions": 0})
        report = evaluate_gates(ctx, ["RULES_FAIL"])
        assert report.hard_blocks
        assert report.hard_blocks[0].gate_id == "RULES_FAIL"
        assert report.hard_blocks[0].override_allowed is False

    def test_shadow_mode_does_not_reach_the_gate(self, tmp_path):
        write_wf(tmp_path, "ci.yml", MIXED_WF)
        ctx = SessionContext(mode=GDEMode.GATE, project_dir=tmp_path)
        out = gde_run_rules_engine(ctx)
        ctx.engine_results["rules_engine"] = EngineResult(
            engine_id="rules_engine", status=EngineStatus.SUCCESS, output=out)
        assert out["shadow_mode"] is True
        assert out["hard_failure"] is False
        assert evaluate_gates(ctx, ["RULES_FAIL"]).hard_blocks == []


class TestRedTeamRefusesToScaffoldUnpinnedCI:
    def _op(self, payload, path=".github/workflows/release.yml"):
        return WriteOperation(
            engine_id="build_scaffold", operation_id="w1",
            description="scaffold release workflow", target_path=path,
            payload=payload,
        )

    def test_unpinned_scaffold_is_critical(self, tmp_path):
        ctx = SessionContext(project_dir=tmp_path)
        ctx.pending_write_operations = [self._op(MIXED_WF)]
        findings = _check_writes_unpinned_ci(ctx)
        assert len(findings) == 1
        assert findings[0].severity == "critical"
        assert findings[0].category == "unpinned_ci_write"

    def test_pinned_scaffold_is_clean(self, tmp_path):
        ctx = SessionContext(project_dir=tmp_path)
        ctx.pending_write_operations = [self._op(PINNED_WF)]
        assert _check_writes_unpinned_ci(ctx) == []

    def test_non_workflow_writes_are_ignored(self, tmp_path):
        ctx = SessionContext(project_dir=tmp_path)
        ctx.pending_write_operations = [self._op(MIXED_WF, path="docs/example.yml")]
        assert _check_writes_unpinned_ci(ctx) == []

    def test_uninspectable_payload_is_skipped_not_passed(self, tmp_path):
        """A dict payload cannot be read; that is not the same as clean."""
        ctx = SessionContext(project_dir=tmp_path)
        ctx.pending_write_operations = [self._op({"steps": []})]
        assert _check_writes_unpinned_ci(ctx) == []

    def test_evidence_and_inference_stay_separate(self, tmp_path):
        ctx = SessionContext(project_dir=tmp_path)
        ctx.pending_write_operations = [self._op(MIXED_WF)]
        f = _check_writes_unpinned_ci(ctx)[0]
        assert "target_path=" in f.evidence      # observed only
        assert "supply chain" in f.inference     # what follows from it
