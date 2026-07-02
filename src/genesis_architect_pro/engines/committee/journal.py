"""Committee engine — Decision Journal integration.

Appends a structured entry to .genesis/gde_decision_log.jsonl
after every Committee run. Append-only, atomic (tmp→rename),
consistent with the GDE session persistence pattern.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from genesis_architect_pro.engines.committee.types import (
    CommitteeRequest,
    CommitteeResult,
)

_JOURNAL_FILE = ".genesis/gde_decision_log.jsonl"


def append_journal_entry(
    request: CommitteeRequest,
    result: CommitteeResult,
    session_id: str | None = None,
    project_dir: Path | None = None,
) -> Path:
    """Append one Committee entry to the decision journal.

    Args:
        request: The original CommitteeRequest.
        result: The CommitteeResult (post-transparency).
        session_id: GDE session ID (generated if None).
        project_dir: Root of the project (cwd if None).

    Returns:
        Path to the journal file.
    """
    root = project_dir or Path.cwd()
    journal_path = root / _JOURNAL_FILE
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    entry = _build_entry(request, result, session_id or str(uuid.uuid4()))
    _atomic_append(journal_path, entry)
    return journal_path


def _build_entry(
    request: CommitteeRequest,
    result: CommitteeResult,
    session_id: str,
) -> dict:
    entry: dict = {
        "session_id": session_id,
        "engine": "committee",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": request.question,
        "mode": request.mode.value,
        "verdict": result.verdict,
        "confidence": round(result.confidence, 4),
        "consensus_type": result.consensus_type.value,
        "rounds_run": result.rounds_run,
        "transparency": request.transparency.value,
        "advisor_count": 5,
    }

    if result.minority_view:
        entry["minority_view"] = result.minority_view

    if result.manufactured_warning:
        entry["manufactured_warning"] = result.manufactured_warning

    # what_would_change_it: collect from advisor positions (PRO only)
    if result.advisor_positions:
        changes = [
            p.what_would_change_it
            for p in result.advisor_positions
            if p.what_would_change_it
        ]
        if changes:
            entry["what_would_change_it"] = changes[0]  # strongest signal

    if result.voting_record:
        entry["voting"] = {
            "for": result.voting_record.for_,
            "against": result.voting_record.against,
            "abstain": result.voting_record.abstain,
        }

    return entry


def _atomic_append(path: Path, entry: dict) -> None:
    """Atomically append one JSON line to path.

    Uses a temp file + rename to avoid partial writes on crash.
    """
    line = json.dumps(entry, ensure_ascii=False) + "\n"

    # Read existing content
    existing = b""
    if path.exists():
        existing = path.read_bytes()

    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(existing + line.encode("utf-8"))
    os.replace(tmp, path)
