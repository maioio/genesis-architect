"""Genesis Decision Engine — SessionContext persistence.

Serialises and deserialises SessionContext to/from
`.genesis/gde_session.json` so sessions can be resumed after a crash
or restart. Also manages `gde_decision_log.jsonl` (append-only).

This module contains no orchestration logic. It only reads and writes
the session file format.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from genesis_architect_pro.gde_types import (
    DecisionEntry,
    EngineResult,
    EngineStatus,
    GateAction,
    GateOutcome,
    GateReport,
    GateResult,
    GDEMode,
    Intent,
    LifecycleStage,
    SessionContext,
    WriteOperation,
)

# Relative to project_dir
_SESSION_FILE = Path(".genesis") / "gde_session.json"
_DECISION_LOG = Path(".genesis") / "gde_decision_log.jsonl"

# Schema version for forward-compatibility detection
_SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _path_to_str(obj: object) -> object:
    """Recursively convert Path objects to strings for JSON serialisation."""
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _path_to_str(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_path_to_str(i) for i in obj]
    return obj


def _serialise_context(ctx: SessionContext) -> dict:
    """Convert a SessionContext to a JSON-serialisable dict."""
    raw = asdict(ctx)
    raw = _path_to_str(raw)
    raw["_schema_version"] = _SCHEMA_VERSION
    return raw


def _deserialise_engine_result(d: dict) -> EngineResult:
    return EngineResult(
        engine_id=d["engine_id"],
        status=EngineStatus(d["status"]),
        output=d.get("output", {}),
        confidence=float(d.get("confidence", 1.0)),
        warnings=d.get("warnings", []),
        error=d.get("error"),
        duration_ms=int(d.get("duration_ms", 0)),
    )


def _deserialise_write_op(d: dict) -> WriteOperation:
    return WriteOperation(
        engine_id=d["engine_id"],
        operation_id=d["operation_id"],
        description=d["description"],
        target_path=d["target_path"],
        is_reversible=bool(d.get("is_reversible", True)),
        payload=d.get("payload"),
    )


def _deserialise_decision_entry(d: dict) -> DecisionEntry:
    return DecisionEntry(
        session_id=d["session_id"],
        timestamp=d["timestamp"],
        stage=LifecycleStage(d["stage"]),
        decision_type=d["decision_type"],
        actor=d["actor"],
        subject=d["subject"],
        detail=d["detail"],
        confidence_before=float(d["confidence_before"]),
        confidence_after=float(d["confidence_after"]),
        outcome=d["outcome"],
    )


def _deserialise_gate_result(d: dict) -> GateResult:
    return GateResult(
        gate_id=d["gate_id"],
        action=GateAction(d["action"]),
        override_allowed=bool(d["override_allowed"]),
        title=d["title"],
        reason=d["reason"],
        detail=d.get("detail", ""),
        confidence_penalty=float(d.get("confidence_penalty", 0.0)),
    )


def _deserialise_gate_report(d: dict) -> GateReport:
    report = GateReport(
        passed=[_deserialise_gate_result(r) for r in d.get("passed", [])],
        warnings=[_deserialise_gate_result(r) for r in d.get("warnings", [])],
        blocks=[_deserialise_gate_result(r) for r in d.get("blocks", [])],
        hard_blocks=[_deserialise_gate_result(r) for r in d.get("hard_blocks", [])],
        overall=GateOutcome(d.get("overall", GateOutcome.PASS)),
    )
    return report


def _deserialise_intent(d: dict | None) -> Intent | None:
    if d is None:
        return None
    return Intent(
        raw_text=d["raw_text"],
        mode=GDEMode(d["mode"]),
        confidence=float(d["confidence"]),
        signals=d.get("signals", []),
        clarifying_questions=d.get("clarifying_questions", []),
        params=d.get("params", {}),
    )


def _deserialise_context(d: dict) -> SessionContext:
    """Reconstruct a SessionContext from a deserialised dict."""
    ctx = SessionContext(
        session_id=d["session_id"],
        mode=GDEMode(d["mode"]),
        stage=LifecycleStage(d["stage"]),
        project_dir=Path(d["project_dir"]),
        import_graph=d.get("import_graph", {}),
        model_state=d.get("model_state", {}),
        session_memory=d.get("session_memory", {}),
        intent=_deserialise_intent(d.get("intent")),
        engine_results={
            k: _deserialise_engine_result(v)
            for k, v in d.get("engine_results", {}).items()
        },
        overall_confidence=float(d.get("overall_confidence", 1.0)),
        project_risk_level=d.get("project_risk_level", "none"),
        pending_write_operations=[
            _deserialise_write_op(w)
            for w in d.get("pending_write_operations", [])
        ],
        decision_log=[
            _deserialise_decision_entry(e)
            for e in d.get("decision_log", [])
        ],
    )
    return ctx


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def save_session(ctx: SessionContext, project_dir: Path) -> None:
    """Persist a SessionContext snapshot to .genesis/gde_session.json.

    Creates .genesis/ if it does not exist. Writes atomically via a
    temp file so a crash mid-write never corrupts the previous snapshot.

    Args:
        ctx: The session context to persist.
        project_dir: Root of the project (the .genesis/ dir lives here).
    """
    genesis_dir = project_dir / ".genesis"
    genesis_dir.mkdir(parents=True, exist_ok=True)

    target = project_dir / _SESSION_FILE
    tmp = target.with_suffix(".tmp")

    payload = _serialise_context(ctx)
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(target)


def load_session(project_dir: Path) -> SessionContext | None:
    """Load a persisted SessionContext from .genesis/gde_session.json.

    Returns None if the file does not exist or cannot be parsed.
    The caller is responsible for deciding whether a loaded session is
    still fresh enough to resume (check ctx.stage, ctx.session_id, etc.).

    Args:
        project_dir: Root of the project.
    """
    target = project_dir / _SESSION_FILE
    if not target.exists():
        return None
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return _deserialise_context(raw)
    except Exception:  # noqa: BLE001
        return None


def delete_session(project_dir: Path) -> None:
    """Delete the persisted session file if it exists."""
    target = project_dir / _SESSION_FILE
    if target.exists():
        target.unlink()


def append_decision_log(entry: DecisionEntry, project_dir: Path) -> None:
    """Append one DecisionEntry to .genesis/gde_decision_log.jsonl.

    The file is created if it does not exist. Each line is one JSON object.
    This function is a no-op (silently skips) on I/O error to ensure the
    decision log never crashes the GDE.

    Args:
        entry: The decision entry to append.
        project_dir: Root of the project.
    """
    genesis_dir = project_dir / ".genesis"
    genesis_dir.mkdir(parents=True, exist_ok=True)

    log_path = project_dir / _DECISION_LOG
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
    except OSError:
        pass


def read_decision_log(project_dir: Path) -> list[DecisionEntry]:
    """Read all entries from .genesis/gde_decision_log.jsonl.

    Returns an empty list if the file does not exist or any line is
    unparseable (corrupt lines are silently skipped).

    Args:
        project_dir: Root of the project.
    """
    log_path = project_dir / _DECISION_LOG
    if not log_path.exists():
        return []

    entries: list[DecisionEntry] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            entries.append(_deserialise_decision_entry(d))
        except Exception:  # noqa: BLE001
            continue
    return entries


def session_file_exists(project_dir: Path) -> bool:
    """Return True if a persisted session file exists for this project."""
    return (project_dir / _SESSION_FILE).exists()
