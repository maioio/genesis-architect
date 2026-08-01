"""Tests for the three production-wiring modules:
  - gde_engine_registration (Step 7a)
  - gde_engine_adapters      (Step 7b)
  - decision_engine APPROVE/COMMIT (Step 7c)
  - gde_cli                  (Step 8)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import json

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(gate_outcome_str: str = "pass", pending_writes=None):
    """Build a minimal SessionReport-like object for testing."""
    from genesis_architect_pro.gde_types import (
        GDEMode, LifecycleStage, GateReport, GateOutcome, GateResult, GateAction,
        SessionReport,
    )

    outcome_map = {
        "pass": GateOutcome.PASS,
        "warn": GateOutcome.WARN,
        "block": GateOutcome.BLOCK,
        "hard_block": GateOutcome.HARD_BLOCK,
    }
    gate_report = GateReport(overall=outcome_map[gate_outcome_str])

    if gate_outcome_str == "hard_block":
        gate_report.hard_blocks = [
            GateResult(
                gate_id="PLAN_WRITE",
                action=GateAction.HARD_BLOCK,
                override_allowed=False,
                title="hard",
                reason="planned.json write blocked",
            )
        ]

    return SessionReport(
        session_id="test-session-id",
        mode=GDEMode.RECOVERY,
        stage=LifecycleStage.REPORT,
        project_risk_level="none",
        overall_confidence=0.90,
        gate_report=gate_report,
        engine_results={},
        decision_log=[],
    )


# ---------------------------------------------------------------------------
# Engine Registration
# ---------------------------------------------------------------------------


class TestEngineRegistration:
    def test_import_does_not_crash(self):
        import genesis_architect_pro.gde_engine_registration  # noqa: F401

    def test_core_engines_registered(self):
        """All original 8 core engines must be registered (registry may have more)."""
        from genesis_architect_pro.engine_registry import get_default_registry
        reg = get_default_registry()
        required = {
            "import_graph", "architecture_scorer", "antipattern_detector",
            "fragility_classifier", "recovery_report", "refactoring_planner",
            "c4_generator", "security_templates",
        }
        registered_ids = set(reg.ids())
        missing = required - registered_ids
        assert not missing, f"Missing core engines: {missing}"

    def test_recovery_phase_order(self):
        from genesis_architect_pro.engine_registry import get_default_registry
        from genesis_architect_pro.gde_types import GDEMode

        reg = get_default_registry()
        groups = reg.parallel_groups_for_mode(GDEMode.RECOVERY)
        # Phase 1 must be import_graph alone
        assert len(groups) >= 1
        phase1_ids = [d.id for d in groups[0]]
        assert "import_graph" in phase1_ids
        # recovery_report must be in a later phase than fragility_classifier
        all_ids = [[d.id for d in g] for g in groups]
        flat = [eid for phase in all_ids for eid in phase]
        assert flat.index("recovery_report") > flat.index("fragility_classifier")

    def test_import_graph_is_required(self):
        from genesis_architect_pro.engine_registry import get_default_registry
        from genesis_architect_pro.gde_types import GDEMode

        reg = get_default_registry()
        descs = {d.id: d for d in reg.ordered_for_mode(GDEMode.RECOVERY)}
        assert descs["import_graph"].is_optional is False

    def test_document_mode_includes_c4(self):
        from genesis_architect_pro.engine_registry import get_default_registry
        from genesis_architect_pro.gde_types import GDEMode

        reg = get_default_registry()
        ids = [d.id for d in reg.ordered_for_mode(GDEMode.DOCUMENT)]
        assert "c4_generator" in ids

    def test_registration_is_idempotent(self):
        """Importing registration twice must not raise or double-register."""
        import importlib
        import genesis_architect_pro.gde_engine_registration as m
        importlib.reload(m)  # second registration pass — should be no-op

    def test_adapters_module_importable(self):
        import genesis_architect_pro.gde_engine_adapters  # noqa: F401


# ---------------------------------------------------------------------------
# Engine Adapters — smoke tests with mocked engines
# ---------------------------------------------------------------------------


class TestEngineAdapters:
    def _ctx(self):
        from genesis_architect_pro.gde_types import SessionContext, GDEMode
        ctx = SessionContext(mode=GDEMode.RECOVERY)
        ctx.project_dir = Path(tempfile.mkdtemp())
        return ctx

    def test_import_graph_adapter_returns_dict(self):
        from genesis_architect_pro.gde_engine_adapters import gde_run_import_graph
        ctx = self._ctx()
        with patch("genesis_architect_pro.import_graph.load_or_build") as mock_load:
            mock_graph = MagicMock()
            mock_graph.cycles = []
            mock_graph.dark_modules = []
            mock_graph.layer_map = {}
            mock_load.return_value = mock_graph
            result = gde_run_import_graph(ctx)
        assert "graph" in result
        assert "cycles" in result
        assert "_confidence" in result

    def test_import_graph_adapter_handles_exception(self):
        from genesis_architect_pro.gde_engine_adapters import gde_run_import_graph
        ctx = self._ctx()
        with patch("genesis_architect_pro.import_graph.load_or_build", side_effect=RuntimeError("fail")):
            result = gde_run_import_graph(ctx)
        assert result["_confidence"] < 1.0
        assert result["_warnings"]

    def test_architecture_scorer_adapter_handles_exception(self):
        from genesis_architect_pro.gde_engine_adapters import gde_run_architecture_scorer
        ctx = self._ctx()
        with patch("genesis_architect_pro.architecture_scorer.score_project", side_effect=RuntimeError("fail")):
            result = gde_run_architecture_scorer(ctx)
        assert result["_confidence"] < 1.0

    def test_antipattern_adapter_handles_exception(self):
        from genesis_architect_pro.gde_engine_adapters import gde_run_antipattern_detector
        ctx = self._ctx()
        with patch("genesis_architect_pro.antipattern_detector.detect_all", side_effect=RuntimeError("fail")):
            result = gde_run_antipattern_detector(ctx)
        assert result["_confidence"] < 1.0

    def test_c4_adapter_handles_exception(self):
        from genesis_architect_pro.gde_engine_adapters import gde_run_c4_generator
        ctx = self._ctx()
        with patch("genesis_architect_pro.c4_generator.generate_c4_doc", side_effect=RuntimeError("fail")):
            result = gde_run_c4_generator(ctx)
        assert result["_confidence"] < 1.0

    def test_security_adapter_returns_paths_on_success(self):
        from genesis_architect_pro.gde_engine_adapters import gde_run_security_templates
        ctx = self._ctx()
        with patch(
            "genesis_architect_pro.security_templates.generate_security_docs",
            return_value={"stride_path": "/a/STRIDE.md", "owasp_path": "/a/OWASP.md"},
        ):
            result = gde_run_security_templates(ctx)
        assert "stride_path" in result
        assert result["_confidence"] == 1.0


# ---------------------------------------------------------------------------
# APPROVE / COMMIT stages
# ---------------------------------------------------------------------------


class TestApproveCommit:
    def test_approve_raises_on_hard_block(self):
        from genesis_architect_pro import GenesisDecisionEngine
        gde = GenesisDecisionEngine(project_dir=Path(tempfile.mkdtemp()))
        report = _make_report("hard_block")
        with pytest.raises(RuntimeError, match="HARD_BLOCK"):
            gde.approve(report)

    def test_approve_returns_approval_request_on_pass(self):
        from genesis_architect_pro import GenesisDecisionEngine
        from genesis_architect_pro.gde_types import ApprovalRequest
        project_dir = Path(tempfile.mkdtemp())
        gde = GenesisDecisionEngine(project_dir=project_dir)
        report = _make_report("pass")
        req = gde.approve(report)
        assert isinstance(req, ApprovalRequest)
        assert req.session_id == report.session_id
        assert "mode=recovery" in req.summary

    def test_commit_reject_returns_success(self):
        from genesis_architect_pro import GenesisDecisionEngine
        from genesis_architect_pro.gde_types import ApprovalDecision, ApprovalChoice, CommitResult
        project_dir = Path(tempfile.mkdtemp())
        gde = GenesisDecisionEngine(project_dir=project_dir)
        report = _make_report("pass")
        decision = ApprovalDecision(
            session_id=report.session_id,
            choice=ApprovalChoice.REJECT,
        )
        result = gde.commit(report, decision)
        assert isinstance(result, CommitResult)
        assert result.success is True
        assert not result.committed

    def test_commit_defer_returns_success_no_writes(self):
        from genesis_architect_pro import GenesisDecisionEngine
        from genesis_architect_pro.gde_types import ApprovalDecision, ApprovalChoice
        project_dir = Path(tempfile.mkdtemp())
        gde = GenesisDecisionEngine(project_dir=project_dir)
        report = _make_report("pass")
        decision = ApprovalDecision(
            session_id=report.session_id,
            choice=ApprovalChoice.DEFER,
        )
        result = gde.commit(report, decision)
        assert result.success is True
        assert not result.committed

    def test_commit_hard_block_returns_failed(self):
        from genesis_architect_pro import GenesisDecisionEngine
        from genesis_architect_pro.gde_types import ApprovalDecision, ApprovalChoice
        project_dir = Path(tempfile.mkdtemp())
        gde = GenesisDecisionEngine(project_dir=project_dir)
        report = _make_report("hard_block")
        decision = ApprovalDecision(
            session_id=report.session_id,
            choice=ApprovalChoice.APPROVE,
        )
        result = gde.commit(report, decision)
        assert result.success is False
        assert result.errors

    def test_commit_approve_executes_write_op(self):
        """End-to-end: write operation with payload is written to disk."""
        from genesis_architect_pro import GenesisDecisionEngine, save_session
        from genesis_architect_pro.gde_types import (
            ApprovalDecision, ApprovalChoice, SessionContext, WriteOperation, GDEMode,
        )

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            gde = GenesisDecisionEngine(project_dir=project_dir)

            # Save a session with a pending write op
            ctx = SessionContext(mode=GDEMode.RECOVERY)
            ctx.pending_write_operations.append(WriteOperation(
                engine_id="test",
                operation_id="op1",
                description="write test file",
                target_path="output/test_output.txt",
                payload="hello from GDE",
            ))
            save_session(ctx, project_dir)

            report = _make_report("pass")
            report.session_id = ctx.session_id

            decision = ApprovalDecision(
                session_id=ctx.session_id,
                choice=ApprovalChoice.APPROVE,
            )
            result = gde.commit(report, decision)
            assert result.success is True

    def test_execute_write_operation_creates_file(self):
        from genesis_architect_pro import GenesisDecisionEngine
        from genesis_architect_pro.gde_types import WriteOperation

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            gde = GenesisDecisionEngine(project_dir=project_dir)
            op = WriteOperation(
                engine_id="test",
                operation_id="op1",
                description="test write",
                target_path="subdir/file.txt",
                payload="content",
            )
            gde._execute_write_operation(op)
            assert (project_dir / "subdir" / "file.txt").read_text() == "content"

    def test_execute_write_operation_json_payload(self):
        from genesis_architect_pro import GenesisDecisionEngine
        from genesis_architect_pro.gde_types import WriteOperation

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            gde = GenesisDecisionEngine(project_dir=project_dir)
            op = WriteOperation(
                engine_id="test",
                operation_id="op2",
                description="json write",
                target_path="data.json",
                payload={"key": "value"},
            )
            gde._execute_write_operation(op)
            content = json.loads((project_dir / "data.json").read_text())
            assert content["key"] == "value"

    def test_execute_write_operation_none_payload_is_noop(self):
        from genesis_architect_pro import GenesisDecisionEngine
        from genesis_architect_pro.gde_types import WriteOperation

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            gde = GenesisDecisionEngine(project_dir=project_dir)
            op = WriteOperation(
                engine_id="test",
                operation_id="op3",
                description="noop",
                target_path="noop.txt",
                payload=None,
            )
            gde._execute_write_operation(op)
            assert not (project_dir / "noop.txt").exists()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    @pytest.fixture(autouse=True)
    def _licensed(self, monkeypatch):
        """The CLI entry point enforces the Pro license; these tests assert
        wiring, not the gate (covered by test_license.py)."""
        monkeypatch.setattr("genesis_architect_pro.license.is_licensed", lambda: True)

    def _run_cli(self, argv, capsys=None):
        from genesis_architect_pro.gde_cli import main
        return main(argv)

    def test_classify_only_returns_zero(self):
        from genesis_architect_pro.gde_cli import main
        rc = main(["decide", "--classify-only", "diagnose the project", "--no-commit"])
        assert rc == 0

    def test_classify_only_recovery_mode(self, capsys):
        from genesis_architect_pro.gde_cli import main
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["decide", "--classify-only", "diagnose and identify drift", "--no-commit"])
        output = buf.getvalue()
        assert "recovery" in output.lower()

    def test_bare_instruction_without_subcommand(self):
        """Bare `genesis <instruction>` (no 'decide' keyword) must work."""
        from genesis_architect_pro.gde_cli import main
        rc = main(["--classify-only", "diagnose the project and identify drift"])
        assert rc == 0

    def test_help_exits_zero(self):
        from genesis_architect_pro.gde_cli import main
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0

    def test_invalid_dir_returns_error(self):
        from genesis_architect_pro.gde_cli import main
        rc = main(["decide", "--classify-only", "diagnose", "--dir", "/nonexistent/path/xyz"])
        assert rc == 1

    def test_unlicensed_cli_is_blocked(self, monkeypatch, capsys):
        """Without a valid license every CLI command exits 2 with guidance."""
        monkeypatch.setattr("genesis_architect_pro.license.is_licensed", lambda: False)
        from genesis_architect_pro.gde_cli import main
        rc = main(["decide", "--classify-only", "diagnose the project"])
        assert rc == 2
        assert "license" in capsys.readouterr().err.lower()

    def test_help_works_without_license(self, monkeypatch):
        monkeypatch.setattr("genesis_architect_pro.license.is_licensed", lambda: False)
        from genesis_architect_pro.gde_cli import main
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0

    # -----------------------------------------------------------------
    # Regression tests for the QA report (genesis-pro-qa-report.md)
    # -----------------------------------------------------------------

    def test_memory_status_does_not_crash_when_empty(self, tmp_path):
        """memory_status() returns {filename: int|False} (flat); cmd_memory
        used to call .get() on that int/bool and crash with AttributeError."""
        from genesis_architect_pro.gde_cli import main
        rc = main(["memory", "--status", "--dir", str(tmp_path)])
        assert rc == 0

    def test_memory_status_does_not_crash_when_populated(self, tmp_path):
        from genesis_architect_pro.gde_cli import main
        assert main(["memory", "--init", "--dir", str(tmp_path)]) == 0
        assert main(["memory", "--status", "--dir", str(tmp_path)]) == 0

    def test_ui_writes_workspace_file(self, tmp_path):
        """write_workspace(project_root, out_name) recomputes state itself;
        cmd_ui used to pass it (WorkspaceState, Path) and crash with TypeError."""
        from genesis_architect_pro.gde_cli import main
        rc = main(["ui", "--dir", str(tmp_path)])
        assert rc == 0
        assert (tmp_path / ".genesis" / "ui" / "workspace.html").is_file()

    def test_doctor_runs_without_license_and_reports_missing(self, monkeypatch):
        monkeypatch.setattr("genesis_architect_pro.license.is_licensed", lambda: False)
        from genesis_architect_pro.gde_cli import main
        rc = main(["doctor"])
        assert rc == 1

    def test_doctor_runs_with_license_and_reports_ready(self):
        from genesis_architect_pro.gde_cli import main
        rc = main(["doctor"])
        assert rc == 0

    def test_license_activate_invalid_key_fails_cleanly(self, capsys):
        from genesis_architect_pro.gde_cli import main
        rc = main(["license", "activate", "gpro_not-a-real-key.bad"])
        assert rc == 1
        captured = capsys.readouterr()
        assert "invalid" in (captured.out + captured.err).lower()

    def test_license_activate_valid_key_writes_file(self, tmp_path, monkeypatch):
        """Uses a monkeypatched parse_key rather than a real signed key — the
        private signing key deliberately never lives in this package (see
        license.py). The Docker QA simulation covers the real Ed25519 path
        end-to-end with an actual signed test key."""
        fake_file = tmp_path / "pro_license"
        monkeypatch.setattr("genesis_architect_pro.license.LICENSE_FILE", fake_file)
        monkeypatch.setattr("genesis_architect_pro.license.parse_key",
                            lambda key: {"sub": "test@example.com"})
        from genesis_architect_pro.gde_cli import main
        rc = main(["license", "activate", "gpro_fake.fake"])
        assert rc == 0
        assert fake_file.is_file()
        assert "gpro_fake.fake" in fake_file.read_text(encoding="utf-8")

    def test_license_status_reports_active(self, monkeypatch, capsys):
        monkeypatch.setattr("genesis_architect_pro.license.is_licensed", lambda: True)
        from genesis_architect_pro.gde_cli import main
        rc = main(["license", "status"])
        assert rc == 0
        assert "active" in capsys.readouterr().out.lower()

    def test_license_status_reports_inactive(self, monkeypatch, capsys):
        monkeypatch.setattr("genesis_architect_pro.license.is_licensed", lambda: False)
        from genesis_architect_pro.gde_cli import main
        rc = main(["license", "status"])
        assert rc == 1
        assert "not active" in capsys.readouterr().out.lower()

    def test_recover_command_classifies_as_recovery_high_confidence(self, tmp_path, capsys):
        """genesis recover <path> is a thin wrapper around decide — the site
        advertises it as a literal single/two-word command."""
        from genesis_architect_pro.gde_cli import main
        rc = main(["recover", str(tmp_path), "--classify-only"])
        assert rc == 0
        out = capsys.readouterr().out.lower()
        assert "recovery" in out

    def test_harden_command_classifies_as_gate(self, tmp_path, capsys):
        from genesis_architect_pro.gde_cli import main
        rc = main(["harden", str(tmp_path), "--classify-only"])
        assert rc == 0
        out = capsys.readouterr().out.lower()
        assert "gate" in out

    def test_unknown_single_word_command_is_rejected(self, capsys):
        """A mistyped/unregistered single-word command (e.g. 'doctr', or the
        website's old 'harden'/'recover'/'doctor' before they were wired up)
        must not be silently swallowed into a low-confidence decide guess."""
        from genesis_architect_pro.gde_cli import main
        rc = main(["doctr"])
        assert rc == 1
        assert "unknown command" in capsys.readouterr().err.lower()

    def test_terse_real_word_still_routes_to_decide(self):
        """A single word that matches at least one intent signal (unlike a
        typo) must still fall through to decide, not the unknown-command guard."""
        from genesis_architect_pro.gde_cli import main
        rc = main(["--classify-only", "refactor"])
        assert rc == 0

    def test_flag_as_first_token_still_routes_to_decide(self):
        """Regression guard: a leading flag like --classify-only (from a bare
        `genesis --classify-only "..."` invocation) must never be mistaken
        for an unknown command token."""
        from genesis_architect_pro.gde_cli import main
        rc = main(["--classify-only", "diagnose the project and identify drift"])
        assert rc == 0


# ---------------------------------------------------------------------------
# New mode wiring — RESEARCH, BUILD, COMMITTEE
# ---------------------------------------------------------------------------


class TestNewModeWiring:
    def test_all_7_modes_have_engines(self):
        """All GDE modes must have at least one engine registered."""
        from genesis_architect_pro.engine_registry import get_default_registry
        from genesis_architect_pro.gde_types import GDEMode

        reg = get_default_registry()
        for mode in GDEMode:
            groups = reg.parallel_groups_for_mode(mode)
            n = sum(len(g) for g in groups)
            assert n >= 1, f"Mode {mode.value} has no engines registered"

    def test_13_engines_total(self):
        from genesis_architect_pro.engine_registry import get_default_registry

        reg = get_default_registry()
        assert len(reg._descriptors) >= 13

    def test_research_mode_phases(self):
        from genesis_architect_pro.engine_registry import get_default_registry
        from genesis_architect_pro.gde_types import GDEMode

        reg = get_default_registry()
        groups = reg.parallel_groups_for_mode(GDEMode.RESEARCH)
        ids = {d.id for phase in groups for d in phase}
        assert "source_registry" in ids
        assert "field_intelligence" in ids
        assert "evidence_pack" in ids

    def test_build_mode_has_scaffold_engine(self):
        from genesis_architect_pro.engine_registry import get_default_registry
        from genesis_architect_pro.gde_types import GDEMode

        reg = get_default_registry()
        groups = reg.parallel_groups_for_mode(GDEMode.BUILD)
        ids = {d.id for phase in groups for d in phase}
        assert "build_scaffold" in ids

    def test_committee_mode_includes_analysis_and_synthesis(self):
        from genesis_architect_pro.engine_registry import get_default_registry
        from genesis_architect_pro.gde_types import GDEMode

        reg = get_default_registry()
        groups = reg.parallel_groups_for_mode(GDEMode.COMMITTEE)
        ids = {d.id for phase in groups for d in phase}
        assert "import_graph" in ids
        assert "committee_analysis" in ids

    def test_source_registry_adapter_handles_exception(self):
        from genesis_architect_pro.gde_engine_adapters import gde_run_source_registry
        from genesis_architect_pro.gde_types import GDEMode, SessionContext

        with tempfile.TemporaryDirectory() as tmp:
            ctx = SessionContext(mode=GDEMode.RESEARCH)
            ctx.project_dir = Path(tmp)
            result = gde_run_source_registry(ctx)
            assert isinstance(result, dict)
            assert "_confidence" in result

    def test_field_intelligence_adapter_handles_exception(self):
        from genesis_architect_pro.gde_engine_adapters import gde_run_field_intelligence
        from genesis_architect_pro.gde_types import GDEMode, SessionContext
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            ctx = SessionContext(mode=GDEMode.RESEARCH)
            ctx.project_dir = Path(tmp)
            ctx.instruction = "test tool"

            with patch("genesis_architect_pro.field_intelligence.run_field_workflow",
                       side_effect=RuntimeError("network unavailable")):
                result = gde_run_field_intelligence(ctx)

            assert isinstance(result, dict)
            assert result["_confidence"] <= 0.5
            assert result["findings"] == []

    def test_committee_adapter_returns_perspectives(self):
        from genesis_architect_pro.gde_engine_adapters import gde_run_committee_analysis
        from genesis_architect_pro.gde_types import GDEMode, SessionContext

        with tempfile.TemporaryDirectory() as tmp:
            ctx = SessionContext(mode=GDEMode.COMMITTEE)
            ctx.project_dir = Path(tmp)
            # No engine results — should still return without crashing
            result = gde_run_committee_analysis(ctx)
            assert isinstance(result, dict)
            assert "perspectives" in result
            assert "perspective_count" in result
            assert isinstance(result["_confidence"], float)

    def test_committee_adapter_with_upstream_results(self):
        from genesis_architect_pro.gde_engine_adapters import gde_run_committee_analysis
        from genesis_architect_pro.gde_types import (
            GDEMode, SessionContext, EngineResult, EngineStatus
        )

        with tempfile.TemporaryDirectory() as tmp:
            ctx = SessionContext(mode=GDEMode.COMMITTEE)
            ctx.project_dir = Path(tmp)

            # Inject a fake upstream engine result
            ctx.engine_results["architecture_scorer"] = EngineResult(
                engine_id="architecture_scorer",
                status=EngineStatus.SUCCESS,
                output={"score": 72, "score_label": "Good"},
                confidence=0.9,
            )

            result = gde_run_committee_analysis(ctx)
            assert result["perspective_count"] >= 1
            assert any(p["lens"] == "Architecture" for p in result["perspectives"])

    def test_build_scaffold_adapter_missing_vision(self):
        from genesis_architect_pro.gde_engine_adapters import gde_run_build_scaffold
        from genesis_architect_pro.gde_types import GDEMode, SessionContext

        with tempfile.TemporaryDirectory() as tmp:
            ctx = SessionContext(mode=GDEMode.BUILD)
            ctx.project_dir = Path(tmp)
            ctx.instruction = ""  # no vision
            result = gde_run_build_scaffold(ctx)
            assert result["_confidence"] <= 0.3
            assert "BUILD mode requires" in result["_warnings"][0]
