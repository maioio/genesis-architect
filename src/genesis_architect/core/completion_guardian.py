#!/usr/bin/env python3
"""completion_guardian.py - optional FINAL-verification bridge to Completion Guardian.

Completion Guardian (https://github.com/maioio/completion-guardian) is an optional,
external completeness auditor. Genesis never vendors it, installs it or depends on it.
This module only answers three questions for the Genesis agent workflow:

  1. Is the `project-completeness-audit` skill installed? (fail open if not)
  2. May Genesis mark the exact project state as final-audited? (never without a clear audit)
  3. Did the mark really take effect? (asked of Guardian, not assumed)

The fingerprint, audit state and anti-loop logic stay inside Guardian. Genesis only calls
its documented `status` and `mark` subcommands and keeps one small attestation file.

Commands (JSON on stdout):
  detect   --project P            availability + normalized status
  begin    --project P            FINAL audit is about to run; remember the audited state
  record   --project P --verdict clear|findings
  finalize --project P            mark final, only after a clear audit of the unchanged state

Exit codes: 0 proceed, 3 blocked (audit missing, findings, or state changed), 4 degraded
(Guardian unusable; Genesis falls back to its own gates and no mark is made).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SKILL_NAME = "project-completeness-audit"
ENV_OVERRIDE = "GENESIS_COMPLETION_GUARDIAN_DIR"
STATE_ENV = "GENESIS_COMPLETION_STATE_DIR"
TIMEOUT = 60

EXIT_OK, EXIT_BLOCKED, EXIT_DEGRADED = 0, 3, 4


def _is_skill_dir(path: Path) -> bool:
    return (path / "scripts" / "guardian.py").is_file()


def locate(project: Path) -> Path | None:
    """Return the installed skill directory, or None. Documented locations only."""
    candidates: list[Path] = []
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        candidates.append(Path(override))
    candidates.append(project / ".claude" / "skills" / SKILL_NAME)
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(config) if config else Path.home() / ".claude"
    candidates.append(base / "skills" / SKILL_NAME)
    return next((c for c in candidates if _is_skill_dir(c)), None)


def _run(skill: Path, project: Path, *args: str) -> dict[str, Any]:
    """Run a Guardian subcommand; raise ValueError on any failure or non-JSON object."""
    cmd = [sys.executable, "-I", str(skill / "scripts" / "guardian.py"), *args]
    try:
        proc = subprocess.run(cmd, cwd=project, capture_output=True, text=True,
                              timeout=TIMEOUT, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"guardian could not run: {type(exc).__name__}") from exc
    if proc.returncode != 0:
        raise ValueError(f"guardian exited {proc.returncode}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("guardian output is not JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("guardian output is not an object")
    return data


def _status(skill: Path, project: Path) -> dict[str, Any]:
    data = _run(skill, project, "status", "--project", str(project))
    fingerprint = data.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise ValueError("guardian status has no fingerprint")
    for key in ("audited_current_state", "audited_final_current_state"):
        if not isinstance(data.get(key), bool):
            raise ValueError(f"guardian status field {key} is missing or not boolean")
    return data


def _attestation_path(project: Path) -> Path:
    """Kept outside the project so it can never change Guardian's project fingerprint."""
    root = os.environ.get(STATE_ENV)
    base = Path(root) if root else Path.home() / ".genesis" / "completion-audit"
    return base / (hashlib.sha1(str(project).encode("utf-8")).hexdigest() + ".json")


def _read_attestation(project: Path) -> dict[str, Any]:
    try:
        data = json.loads(_attestation_path(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_attestation(project: Path, data: dict[str, Any]) -> None:
    path = _attestation_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _result(action: str, code: int, **extra: Any) -> tuple[dict[str, Any], int]:
    return {"action": action, **extra}, code


def _unavailable() -> tuple[dict[str, Any], int]:
    return _result("proceed_without_guardian", EXIT_OK, available=False,
                   note="Completion Guardian not installed; existing Genesis final gates apply.")


def _degraded(why: str) -> tuple[dict[str, Any], int]:
    return _result("degraded_use_genesis_gates", EXIT_DEGRADED, available=True, reason=why,
                   note="Guardian unusable; no audited state was recorded. Report this degradation.")


def detect(project: Path) -> tuple[dict[str, Any], int]:
    skill = locate(project)
    if skill is None:
        return _unavailable()
    try:
        status = _status(skill, project)
    except ValueError as exc:
        return _degraded(str(exc))
    return _result("available", EXIT_OK, available=True, fingerprint=status["fingerprint"],
                   audited_current_state=status["audited_current_state"],
                   audited_final_current_state=status["audited_final_current_state"])


def begin(project: Path) -> tuple[dict[str, Any], int]:
    skill = locate(project)
    if skill is None:
        return _unavailable()
    try:
        status = _status(skill, project)
    except ValueError as exc:
        return _degraded(str(exc))
    _write_attestation(project, {"fingerprint": status["fingerprint"], "verdict": None,
                                 "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    return _result("run_final_audit", EXIT_OK, available=True, fingerprint=status["fingerprint"],
                   note=f"Run the {SKILL_NAME} skill in FINAL mode, then record the verdict.")


def record(project: Path, verdict: str) -> tuple[dict[str, Any], int]:
    if verdict not in ("clear", "findings"):
        raise ValueError("verdict must be clear or findings")
    att = _read_attestation(project)
    if not att.get("fingerprint"):
        return _result("blocked_no_audit_started", EXIT_BLOCKED,
                       note="Run `begin` before recording an audit verdict.")
    att["verdict"] = verdict
    _write_attestation(project, att)
    if verdict == "findings":
        return _result("fix_findings", EXIT_BLOCKED,
                       note="Findings are verification failures: fix them, then begin a new audit.")
    return _result("audit_recorded_clear", EXIT_OK, fingerprint=att["fingerprint"])


def finalize(project: Path) -> tuple[dict[str, Any], int]:
    skill = locate(project)
    if skill is None:
        return _unavailable()
    att = _read_attestation(project)
    if att.get("verdict") != "clear" or not att.get("fingerprint"):
        return _result("blocked_no_clear_audit", EXIT_BLOCKED, available=True,
                       note="No clear FINAL audit is recorded for this project; nothing was marked.")
    try:
        before = _status(skill, project)
    except ValueError as exc:
        return _degraded(str(exc))
    if before["fingerprint"] != att["fingerprint"]:
        return _result("blocked_state_changed", EXIT_BLOCKED, available=True,
                       note="The project changed after the audit; re-run the FINAL audit.")
    try:
        _run(skill, project, "mark", "--mode", "final", "--project", str(project))
        after = _status(skill, project)
    except ValueError as exc:
        return _degraded(str(exc))
    if not (after["audited_current_state"] and after["audited_final_current_state"]):
        return _degraded("mark did not produce a final audited state")
    try:
        _attestation_path(project).unlink()
    except OSError:
        pass
    return _result("final_marked", EXIT_OK, available=True, fingerprint=after["fingerprint"],
                   audited_final_current_state=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Optional Completion Guardian FINAL-audit bridge.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("detect", "begin", "record", "finalize"):
        sp = sub.add_parser(name)
        sp.add_argument("--project", default=".")
        if name == "record":
            sp.add_argument("--verdict", required=True, choices=["clear", "findings"])
    args = ap.parse_args(argv)
    project = Path(args.project).resolve()
    if args.cmd == "record":
        payload, code = record(project, args.verdict)
    else:
        payload, code = {"detect": detect, "begin": begin, "finalize": finalize}[args.cmd](project)
    print(json.dumps(payload, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
