"""P1 - Governance Foundation tests. Orchestration infrastructure only."""
import pytest

from genesis_architect_pro.governance import (
    LifecyclePhase, AutonomyLevel, GateDecision, EngineResult, SessionContext,
    Engine, EngineSpec, EngineRegistry,
    ApprovalGate, GatePolicy,
    DecisionEngine, Decision, Alternative,
    Orchestrator, LifecycleStateMachine,
)


# --- a tiny in-test engine that satisfies the Engine contract ---
class _FakeEngine:
    def __init__(self, name, ok=True):
        self.name = name
        self._ok = ok
        self.ran = False

    def available(self):
        return True

    def run(self, ctx):
        self.ran = True
        return EngineResult(engine=self.name, ok=self._ok, data={"phase": ctx.phase.value})


class TestLifecycle:
    def test_phase_order(self):
        order = [p.value for p in LifecyclePhase.order()]
        assert order == ["intake", "plan", "execute", "gate", "report", "approve", "commit"]

    def test_state_machine_advances(self):
        sm = LifecycleStateMachine()
        assert sm.next_phase(LifecyclePhase.INTAKE) is LifecyclePhase.PLAN
        assert sm.next_phase(LifecyclePhase.COMMIT) is None
        assert sm.is_terminal(LifecyclePhase.COMMIT)
        assert not sm.is_terminal(LifecyclePhase.INTAKE)


class TestRegistry:
    def test_register_and_query_by_phase(self):
        reg = EngineRegistry()
        reg.register(EngineSpec(name="e1", engine=_FakeEngine("e1"),
                                phases=["execute"], tier="pro"))
        assert "e1" in reg
        assert len(reg.for_phase("execute")) == 1
        assert len(reg.for_phase("plan")) == 0

    def test_duplicate_registration_rejected(self):
        reg = EngineRegistry()
        spec = EngineSpec(name="e1", engine=_FakeEngine("e1"))
        reg.register(spec)
        with pytest.raises(ValueError):
            reg.register(spec)

    def test_by_tier(self):
        reg = EngineRegistry()
        reg.register(EngineSpec(name="f", engine=_FakeEngine("f"), tier="free"))
        reg.register(EngineSpec(name="p", engine=_FakeEngine("p"), tier="pro"))
        assert [s.name for s in reg.by_tier("free")] == ["f"]


class TestEngineContract:
    def test_fake_engine_satisfies_protocol(self):
        assert isinstance(_FakeEngine("x"), Engine)


class TestGates:
    def test_dangerous_always_needs_approval_even_autonomous(self):
        p = GatePolicy()
        assert p.evaluate(dangerous=True, first_build=False,
                          autonomy=AutonomyLevel.AUTONOMOUS) is GateDecision.NEEDS_APPROVAL

    def test_first_build_gated_unless_autonomous(self):
        p = GatePolicy()
        assert p.evaluate(dangerous=False, first_build=True,
                          autonomy=AutonomyLevel.GUIDED) is GateDecision.NEEDS_APPROVAL
        assert p.evaluate(dangerous=False, first_build=True,
                          autonomy=AutonomyLevel.AUTONOMOUS) is GateDecision.PASS

    def test_routine_passes_above_guided(self):
        p = GatePolicy()
        assert p.evaluate(dangerous=False, first_build=False,
                          autonomy=AutonomyLevel.TRUSTED) is GateDecision.PASS

    def test_default_approver_denies(self):
        gate = ApprovalGate()  # default approver = deny
        ctx = SessionContext(autonomy=AutonomyLevel.GUIDED)
        assert gate.check("execute", ctx, dangerous=True) is GateDecision.BLOCK

    def test_approver_can_grant(self):
        gate = ApprovalGate(approver=lambda action, ctx: True)
        ctx = SessionContext(autonomy=AutonomyLevel.GUIDED)
        assert gate.check("execute", ctx, dangerous=True) is GateDecision.PASS


class TestDecisionEngine:
    def test_no_alternatives(self):
        d = DecisionEngine().decide("q", [])
        assert d.choice is None and d.confidence == "low"

    def test_picks_highest_scored(self):
        alts = [
            Alternative(name="A", pros=["x"], cons=["y", "z"]),
            Alternative(name="B", pros=["x", "y", "z"], evidence_refs=["url1", "url2"]),
        ]
        d = DecisionEngine().decide("which?", alts)
        assert d.choice == "B"
        assert d.what_would_change_it

    def test_high_confidence_requires_evidence(self):
        # big gap but zero evidence -> capped at medium (honesty)
        alts = [Alternative(name="A", pros=["1", "2", "3", "4"]),
                Alternative(name="B")]
        d = DecisionEngine().decide("q", alts)
        assert d.confidence in ("medium", "low")  # not high without evidence

    def test_close_alternatives_flag_committee(self):
        alts = [Alternative(name="A", pros=["x"]), Alternative(name="B", pros=["y"])]
        d = DecisionEngine().decide("q", alts)
        assert d.needs_committee is True


class TestOrchestrator:
    def test_runs_full_lifecycle_no_engines(self):
        """Safe no-op skeleton: no engines registered -> lifecycle completes."""
        orch = Orchestrator(gate=ApprovalGate(approver=lambda a, c: True))
        ctx = orch.run(SessionContext(task="noop", autonomy=AutonomyLevel.TRUSTED))
        assert "committed" in ctx.history[-1] or ctx.phase is LifecyclePhase.COMMIT

    def test_engine_runs_in_its_phase(self):
        reg = EngineRegistry()
        eng = _FakeEngine("exec-engine")
        reg.register(EngineSpec(name="exec-engine", engine=eng, phases=["execute"]))
        orch = Orchestrator(registry=reg,
                            gate=ApprovalGate(approver=lambda a, c: True))
        ctx = orch.run(SessionContext(task="t", autonomy=AutonomyLevel.TRUSTED))
        assert eng.ran
        assert ctx.results["exec-engine"].ok

    def test_blocked_execute_stops_lifecycle(self):
        reg = EngineRegistry()
        reg.register(EngineSpec(name="d", engine=_FakeEngine("d"),
                                phases=["execute"], dangerous=True))
        orch = Orchestrator(registry=reg, gate=ApprovalGate())  # default deny
        ctx = orch.run(SessionContext(task="t", autonomy=AutonomyLevel.GUIDED))
        assert any("blocked at EXECUTE" in h for h in ctx.history)

    def test_failing_engine_degrades_not_raises(self):
        reg = EngineRegistry()
        reg.register(EngineSpec(name="bad", engine=_FakeEngine("bad", ok=False),
                                phases=["plan"]))
        orch = Orchestrator(registry=reg,
                            gate=ApprovalGate(approver=lambda a, c: True))
        ctx = orch.run(SessionContext(task="t", autonomy=AutonomyLevel.TRUSTED))
        assert ctx.results["bad"].ok is False  # recorded, did not raise
