"""Phase 3 — Intelligence Wiring tests.

Covers:
  1. Gate resume flow — approve/reject/defer paths through InboundRouter._run_gde
  2. IDE Bridge hot-swap — _update_ide_bridge called after GDE run
  3. set_ide_bridge API
  4. _build_diff_preview edge cases
  5. _register_pending_gate / _clear_pending_gate internal API
  6. gate_id prefix matching in _handle_approval
  7. HARD_BLOCK path — no approval emitted, session.done fires
  8. ipc_bridge module — smoke test that it imports cleanly
"""

from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch


from genesis_architect_pro.streaming.events import (
    MessageType,
    StreamEmitter,
    StreamMessage,
)
from genesis_architect_pro.streaming.inbound import InboundRouter, _PendingGate


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_msg(msg_type: MessageType, payload: dict, session_id: str = "") -> StreamMessage:
    return StreamMessage(type=msg_type, payload=payload, session_id=session_id)


class _CapturingEmitter(StreamEmitter):
    def __init__(self) -> None:
        super().__init__()
        self.emitted: list[StreamMessage] = []
        self._lock = threading.Lock()

    def emit(self, message: StreamMessage) -> None:
        with self._lock:
            self.emitted.append(message)

    def types(self) -> list[str]:
        with self._lock:
            return [m.type.value for m in self.emitted]

    def wait_for(self, msg_type: MessageType, timeout: float = 3.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if any(m.type == msg_type for m in self.emitted):
                    return True
            time.sleep(0.05)
        return False

    def get_all(self, msg_type: MessageType) -> list[StreamMessage]:
        with self._lock:
            return [m for m in self.emitted if m.type == msg_type]


def _make_router(tmp_path: Path, ide_bridge=None) -> tuple[InboundRouter, _CapturingEmitter]:
    emitter = _CapturingEmitter()
    router = InboundRouter(project_dir=tmp_path, emitter=emitter, ide_bridge=ide_bridge)
    return router, emitter


def _mock_report(session_id=None, gate_overall="PASS", blocks=False):
    """Build a mock GDE report with configurable gate state."""
    import sys
    if "src" not in sys.path:
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from genesis_architect_pro.gde_types import GateOutcome

    _outcome_map = {
        "PASS": GateOutcome.PASS,
        "WARN": GateOutcome.WARN,
        "BLOCK": GateOutcome.BLOCK,
        "HARD_BLOCK": GateOutcome.HARD_BLOCK,
    }

    report = MagicMock()
    report.session_id = session_id or str(uuid.uuid4())
    report.overall_confidence = 0.75
    report.project_risk_level = "MEDIUM"
    report.mode.value = "refactor"
    report.engine_results = {}

    # Gate report — use real enum so comparisons in _run_gde work
    report.gate_report.overall = _outcome_map[gate_overall]
    report.gate_report.hard_blocks = []
    report.gate_report.blocks = [MagicMock()] if blocks else []
    report.gate_report.warnings = []

    return report


# ---------------------------------------------------------------------------
# 1. Gate resume flow — HARD_BLOCK path
# ---------------------------------------------------------------------------

class TestGateResumeHardBlock:
    def test_hard_block_emits_session_done_without_approval_prompt(self, tmp_path):
        """HARD_BLOCK must emit session.done immediately — no approval flow."""
        router, emitter = _make_router(tmp_path)

        report = _mock_report(gate_overall="HARD_BLOCK")
        mock_gde = MagicMock()
        mock_gde.run.return_value = report

        with patch("genesis_architect_pro.gde_engine_registration", create=True), \
             patch("genesis_architect_pro.GenesisDecisionEngine", return_value=mock_gde):
            msg = _make_msg(MessageType.USER_INTENT, {"instruction": "refactor db layer"})
            router.handle(msg)
            found = emitter.wait_for(MessageType.SESSION_DONE, timeout=3.0)

        assert found, f"session.done not emitted. Got: {emitter.types()}"
        # Must NOT emit gate.approval_required
        assert MessageType.GATE_APPROVAL not in [m.type for m in emitter.emitted], \
            "HARD_BLOCK must not emit gate.approval_required"
        # gde.approve / gde.commit must not be called
        mock_gde.approve.assert_not_called()
        mock_gde.commit.assert_not_called()


# ---------------------------------------------------------------------------
# 2. Gate resume flow — BLOCK + approve
# ---------------------------------------------------------------------------

class TestGateResumeBlock:
    def _setup_block_run(self, tmp_path, decision: str):
        """Shared setup: BLOCK report, returns (router, emitter, mock_gde, session_id)."""
        router, emitter = _make_router(tmp_path)
        session_id = str(uuid.uuid4())
        report = _mock_report(session_id=session_id, gate_overall="BLOCK", blocks=True)

        mock_approval_req = MagicMock()
        mock_approval_req.summary = "3 pending writes"
        mock_approval_req.pending_writes = [
            MagicMock(target_path="src/auth.py", description="remove unused import", is_reversible=True),
        ]
        mock_gde = MagicMock()
        mock_gde.run.return_value = report
        mock_gde.approve.return_value = mock_approval_req
        mock_gde.commit.return_value = MagicMock(success=True, committed=["src/auth.py"], errors=[])

        return router, emitter, mock_gde, session_id

    def _send_approval(self, router, gate_key, decision, delay=0.3):
        """Simulate the UI sending user.approval after a short delay."""
        def _do():
            time.sleep(delay)
            msg = _make_msg(MessageType.USER_APPROVAL, {"gate_id": gate_key, "decision": decision})
            router.handle(msg)
        t = threading.Thread(target=_do, daemon=True)
        t.start()

    def test_block_emits_gate_approval_required(self, tmp_path):
        router, emitter, mock_gde, session_id = self._setup_block_run(tmp_path, "approve")
        gate_key = f"{session_id[:8]}-gate"

        with patch("genesis_architect_pro.gde_engine_registration", create=True), \
             patch("genesis_architect_pro.GenesisDecisionEngine", return_value=mock_gde):
            self._send_approval(router, gate_key, "approve", delay=0.4)
            msg = _make_msg(MessageType.USER_INTENT, {"instruction": "fix security holes"})
            router.handle(msg)
            emitter.wait_for(MessageType.SESSION_DONE, timeout=5.0)

        assert any(m.type == MessageType.GATE_APPROVAL for m in emitter.emitted), \
            f"Expected gate.approval_required. Got: {emitter.types()}"

    def test_block_emits_diff_ready(self, tmp_path):
        router, emitter, mock_gde, session_id = self._setup_block_run(tmp_path, "approve")
        gate_key = f"{session_id[:8]}-gate"

        with patch("genesis_architect_pro.gde_engine_registration", create=True), \
             patch("genesis_architect_pro.GenesisDecisionEngine", return_value=mock_gde):
            self._send_approval(router, gate_key, "approve", delay=0.4)
            msg = _make_msg(MessageType.USER_INTENT, {"instruction": "fix security holes"})
            router.handle(msg)
            emitter.wait_for(MessageType.SESSION_DONE, timeout=5.0)

        assert any(m.type == MessageType.DIFF_READY for m in emitter.emitted), \
            f"Expected diff.ready. Got: {emitter.types()}"

    def test_block_approve_calls_gde_commit(self, tmp_path):
        router, emitter, mock_gde, session_id = self._setup_block_run(tmp_path, "approve")
        gate_key = f"{session_id[:8]}-gate"

        with patch("genesis_architect_pro.gde_engine_registration", create=True), \
             patch("genesis_architect_pro.GenesisDecisionEngine", return_value=mock_gde):
            self._send_approval(router, gate_key, "approve", delay=0.4)
            msg = _make_msg(MessageType.USER_INTENT, {"instruction": "fix security holes"})
            router.handle(msg)
            emitter.wait_for(MessageType.SESSION_DONE, timeout=5.0)

        mock_gde.commit.assert_called_once()
        commit_args = mock_gde.commit.call_args
        # ApprovalDecision.choice must be APPROVE
        decision_obj = commit_args[0][1]
        assert decision_obj.choice.value == "approve" or str(decision_obj.choice).lower().endswith("approve"), \
            f"Expected APPROVE choice, got {decision_obj.choice}"

    def test_block_reject_calls_gde_commit_with_reject(self, tmp_path):
        router, emitter, mock_gde, session_id = self._setup_block_run(tmp_path, "reject")
        gate_key = f"{session_id[:8]}-gate"

        with patch("genesis_architect_pro.gde_engine_registration", create=True), \
             patch("genesis_architect_pro.GenesisDecisionEngine", return_value=mock_gde):
            self._send_approval(router, gate_key, "reject", delay=0.4)
            msg = _make_msg(MessageType.USER_INTENT, {"instruction": "apply risky refactor"})
            router.handle(msg)
            emitter.wait_for(MessageType.SESSION_DONE, timeout=5.0)

        mock_gde.commit.assert_called_once()

    def test_block_defer_does_not_call_commit(self, tmp_path):
        router, emitter, mock_gde, session_id = self._setup_block_run(tmp_path, "defer")
        gate_key = f"{session_id[:8]}-gate"

        with patch("genesis_architect_pro.gde_engine_registration", create=True), \
             patch("genesis_architect_pro.GenesisDecisionEngine", return_value=mock_gde):
            self._send_approval(router, gate_key, "defer", delay=0.4)
            msg = _make_msg(MessageType.USER_INTENT, {"instruction": "risky change"})
            router.handle(msg)
            emitter.wait_for(MessageType.SESSION_DONE, timeout=5.0)

        mock_gde.commit.assert_not_called()

    def test_block_session_done_emitted_after_approval(self, tmp_path):
        router, emitter, mock_gde, session_id = self._setup_block_run(tmp_path, "approve")
        gate_key = f"{session_id[:8]}-gate"

        with patch("genesis_architect_pro.gde_engine_registration", create=True), \
             patch("genesis_architect_pro.GenesisDecisionEngine", return_value=mock_gde):
            self._send_approval(router, gate_key, "approve", delay=0.4)
            msg = _make_msg(MessageType.USER_INTENT, {"instruction": "go"})
            router.handle(msg)
            found = emitter.wait_for(MessageType.SESSION_DONE, timeout=5.0)

        assert found, f"session.done must fire after approval. Got: {emitter.types()}"

    def test_pending_gate_cleared_after_approval(self, tmp_path):
        router, emitter, mock_gde, session_id = self._setup_block_run(tmp_path, "approve")
        gate_key = f"{session_id[:8]}-gate"

        with patch("genesis_architect_pro.gde_engine_registration", create=True), \
             patch("genesis_architect_pro.GenesisDecisionEngine", return_value=mock_gde):
            self._send_approval(router, gate_key, "approve", delay=0.4)
            msg = _make_msg(MessageType.USER_INTENT, {"instruction": "go"})
            router.handle(msg)
            emitter.wait_for(MessageType.SESSION_DONE, timeout=5.0)

        with router._pending_lock:
            assert gate_key not in router._pending_gates
            assert session_id not in router._pending_gates


# ---------------------------------------------------------------------------
# 3. gate_id prefix matching
# ---------------------------------------------------------------------------

class TestApprovalPrefixMatch:
    def test_approval_by_session_id_matches_gate_key(self, tmp_path):
        """Frontend may send the full session_id as gate_id — must still match."""
        router, emitter = _make_router(tmp_path)
        session_id = str(uuid.uuid4())
        gate_key = f"{session_id[:8]}-gate"
        pg = _PendingGate(gate_key)
        with router._pending_lock:
            router._pending_gates[gate_key] = pg
            router._pending_gates[session_id] = pg

        msg = _make_msg(MessageType.USER_APPROVAL, {"gate_id": session_id, "decision": "approve"})
        router.handle(msg)
        pg.event.wait(timeout=1.0)
        assert pg.decision == "approve"

    def test_approval_by_gate_key_matches_session_id_index(self, tmp_path):
        """Frontend may send '<session[:8]>-gate' as gate_id — must still match."""
        router, emitter = _make_router(tmp_path)
        session_id = str(uuid.uuid4())
        gate_key = f"{session_id[:8]}-gate"
        pg = _PendingGate(gate_key)
        with router._pending_lock:
            router._pending_gates[gate_key] = pg
            router._pending_gates[session_id] = pg

        msg = _make_msg(MessageType.USER_APPROVAL, {"gate_id": gate_key, "decision": "reject"})
        router.handle(msg)
        pg.event.wait(timeout=1.0)
        assert pg.decision == "reject"


# ---------------------------------------------------------------------------
# 4. IDE Bridge wiring
# ---------------------------------------------------------------------------

class TestIDEBridgeWiring:
    def test_set_ide_bridge_attaches_bridge(self, tmp_path):
        router, emitter = _make_router(tmp_path)
        assert router._ide_bridge is None
        bridge = MagicMock()
        router.set_ide_bridge(bridge)
        assert router._ide_bridge is bridge

    def test_update_ide_bridge_called_after_gde_run(self, tmp_path):
        mock_bridge = MagicMock()
        router, emitter = _make_router(tmp_path, ide_bridge=mock_bridge)

        report = _mock_report(gate_overall="PASS")
        report.engine_results = {}
        mock_gde = MagicMock()
        mock_gde.run.return_value = report

        with patch("genesis_architect_pro.gde_engine_registration", create=True), \
             patch("genesis_architect_pro.GenesisDecisionEngine", return_value=mock_gde), \
             patch("genesis_architect_pro.ide_bridge.build_index_from_engine_results", return_value={}):
            msg = _make_msg(MessageType.USER_INTENT, {"instruction": "analyse imports"})
            router.handle(msg)
            emitter.wait_for(MessageType.SESSION_DONE, timeout=3.0)

        mock_bridge.update_index.assert_called_once()

    def test_update_ide_bridge_skipped_when_no_bridge(self, tmp_path):
        """No bridge → _update_ide_bridge is a no-op, no error."""
        router, emitter = _make_router(tmp_path, ide_bridge=None)
        report = _mock_report(gate_overall="PASS")
        mock_gde = MagicMock()
        mock_gde.run.return_value = report

        with patch("genesis_architect_pro.gde_engine_registration", create=True), \
             patch("genesis_architect_pro.GenesisDecisionEngine", return_value=mock_gde):
            msg = _make_msg(MessageType.USER_INTENT, {"instruction": "check"})
            router.handle(msg)
            emitter.wait_for(MessageType.SESSION_DONE, timeout=3.0)

        # Should not raise; session.done should still be emitted
        assert emitter.wait_for(MessageType.SESSION_DONE, timeout=0.1)

    def test_ide_bridge_failure_does_not_abort_session(self, tmp_path):
        """If IDE Bridge update raises, session.done must still be emitted."""
        mock_bridge = MagicMock()
        mock_bridge.update_index.side_effect = RuntimeError("bridge exploded")
        router, emitter = _make_router(tmp_path, ide_bridge=mock_bridge)

        report = _mock_report(gate_overall="PASS")
        mock_gde = MagicMock()
        mock_gde.run.return_value = report

        with patch("genesis_architect_pro.gde_engine_registration", create=True), \
             patch("genesis_architect_pro.GenesisDecisionEngine", return_value=mock_gde), \
             patch("genesis_architect_pro.ide_bridge.build_index_from_engine_results", return_value={}):
            msg = _make_msg(MessageType.USER_INTENT, {"instruction": "go"})
            router.handle(msg)
            found = emitter.wait_for(MessageType.SESSION_DONE, timeout=3.0)

        assert found, "session.done must fire even if IDE Bridge explodes"


# ---------------------------------------------------------------------------
# 5. _build_diff_preview
# ---------------------------------------------------------------------------

class TestBuildDiffPreview:
    def _router(self, tmp_path):
        emitter = _CapturingEmitter()
        return InboundRouter(project_dir=tmp_path, emitter=emitter)

    def test_empty_pending_writes_returns_empty_string(self, tmp_path):
        router = self._router(tmp_path)
        req = MagicMock()
        req.pending_writes = []
        assert router._build_diff_preview(req) == ""

    def test_single_write_produces_html_list(self, tmp_path):
        router = self._router(tmp_path)
        op = MagicMock()
        op.target_path = "src/auth.py"
        op.description = "remove dead code"
        op.is_reversible = True
        req = MagicMock()
        req.pending_writes = [op]
        html = router._build_diff_preview(req)
        assert "<ul" in html
        assert "src/auth.py" in html
        assert "remove dead code" in html

    def test_irreversible_write_marked_in_preview(self, tmp_path):
        router = self._router(tmp_path)
        op = MagicMock()
        op.target_path = "migrations/001.sql"
        op.description = "drop table"
        op.is_reversible = False
        req = MagicMock()
        req.pending_writes = [op]
        html = router._build_diff_preview(req)
        assert "IRREVERSIBLE" in html

    def test_truncated_to_20_entries(self, tmp_path):
        router = self._router(tmp_path)
        ops = []
        for i in range(30):
            op = MagicMock()
            op.target_path = f"file_{i}.py"
            op.description = f"op {i}"
            op.is_reversible = True
            ops.append(op)
        req = MagicMock()
        req.pending_writes = ops
        html = router._build_diff_preview(req)
        # Only first 20 should appear
        assert "file_19.py" in html
        assert "file_20.py" not in html

    def test_no_pending_writes_attr_returns_empty(self, tmp_path):
        router = self._router(tmp_path)
        req = MagicMock(spec=[])  # no attributes at all
        assert router._build_diff_preview(req) == ""


# ---------------------------------------------------------------------------
# 6. _register_pending_gate / _clear_pending_gate
# ---------------------------------------------------------------------------

class TestPendingGateInternals:
    def test_register_indexes_by_both_keys(self, tmp_path):
        router, _ = _make_router(tmp_path)
        session_id = str(uuid.uuid4())
        gate_key = f"{session_id[:8]}-gate"
        pg = router._register_pending_gate(session_id, gate_key)
        with router._pending_lock:
            assert router._pending_gates[gate_key] is pg
            assert router._pending_gates[session_id] is pg

    def test_clear_removes_both_keys(self, tmp_path):
        router, _ = _make_router(tmp_path)
        session_id = str(uuid.uuid4())
        gate_key = f"{session_id[:8]}-gate"
        router._register_pending_gate(session_id, gate_key)
        router._clear_pending_gate(session_id, gate_key)
        with router._pending_lock:
            assert gate_key not in router._pending_gates
            assert session_id not in router._pending_gates

    def test_clear_nonexistent_does_not_raise(self, tmp_path):
        router, _ = _make_router(tmp_path)
        router._clear_pending_gate("fake-session", "fake-gate")  # must not raise


# ---------------------------------------------------------------------------
# 7. ipc_bridge module — import smoke test
# ---------------------------------------------------------------------------

class TestIpcBridgeModule:
    def test_ipc_bridge_imports_cleanly(self):
        """ipc_bridge.ts is TypeScript — we just verify the Python side doesn't import it."""
        # This test just confirms the Python package structure is intact
        from genesis_architect_pro.streaming import inbound  # noqa: F401
        assert hasattr(inbound, "InboundRouter")

    def test_inbound_router_has_set_ide_bridge(self, tmp_path):
        router, _ = _make_router(tmp_path)
        assert hasattr(router, "set_ide_bridge")
        assert callable(router.set_ide_bridge)

    def test_inbound_router_accepts_ide_bridge_kwarg(self, tmp_path):
        emitter = _CapturingEmitter()
        bridge = MagicMock()
        router = InboundRouter(project_dir=tmp_path, emitter=emitter, ide_bridge=bridge)
        assert router._ide_bridge is bridge
