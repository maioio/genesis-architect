"""genesis decide — CLI entry point for the Genesis Decision Engine.

Usage::

    genesis decide "diagnose the project and identify drift"
    genesis decide "refactor the import module to reduce coupling" --dir /path/to/project
    genesis decide "check compliance" --resume
    genesis decide --classify-only "generate C4 diagrams"

The command runs a full GDE session and prints a human-readable summary.
If write operations are pending and the gate outcome is not HARD_BLOCK, the
user is prompted for approval before any writes are executed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _hr(char: str = "-", width: int = 60) -> str:
    return char * width


def _print_report_summary(report) -> None:  # type: ignore[no-untyped-def]
    gate_label = report.gate_report.overall.value.upper()
    gate_color = {
        "PASS": "\033[32m",
        "WARN": "\033[33m",
        "BLOCK": "\033[33m",
        "HARD_BLOCK": "\033[31m",
    }.get(gate_label, "")
    reset = "\033[0m"

    print(_hr())
    print(f"  Session:    {report.session_id[:12]}…")
    print(f"  Mode:       {report.mode.value}")
    print(f"  Stage:      {report.stage.value}")
    print(f"  Confidence: {report.overall_confidence:.2f}")
    print(f"  Risk:       {report.project_risk_level}")
    print(f"  Gate:       {gate_color}{gate_label}{reset}")
    print()

    if report.gate_report.hard_blocks:
        print("  HARD BLOCKS (non-overridable):")
        for g in report.gate_report.hard_blocks:
            print(f"    [X] [{g.gate_id}] {g.reason}")
    if report.gate_report.blocks:
        print("  BLOCKS (require approval):")
        for g in report.gate_report.blocks:
            print(f"    [!] [{g.gate_id}] {g.reason}")
    if report.gate_report.warnings:
        print("  WARNINGS:")
        for g in report.gate_report.warnings:
            print(f"    [W] [{g.gate_id}] {g.reason}")

    if report.engine_results:
        print()
        print("  Engines:")
        for eid, r in report.engine_results.items():
            conf = f"conf={r.confidence:.2f}" if hasattr(r, "confidence") else ""
            print(f"    {r.status.value:9} {eid}  {conf}")

    print()
    print(f"  Decision log: {len(report.decision_log)} entr{'y' if len(report.decision_log)==1 else 'ies'}")
    print(_hr())


def _prompt_approval(request) -> str:  # type: ignore[no-untyped-def]
    """Interactive approval prompt. Returns 'approve', 'reject', or 'defer'."""
    print()
    print(_hr("="))
    print("  APPROVAL REQUIRED")
    print(_hr("="))
    print(f"  {request.summary}")
    print()
    if request.pending_writes:
        print(f"  Pending write operations ({len(request.pending_writes)}):")
        for op in request.pending_writes:
            rev = "reversible" if op.is_reversible else "IRREVERSIBLE"
            print(f"    [{rev}] {op.target_path}  —  {op.description}")
    else:
        print("  No write operations pending.")
    print()
    print("  [A]pprove  [R]eject  [D]efer (decide later)")
    while True:
        try:
            choice = input("  Choice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "defer"
        if choice in ("a", "approve"):
            return "approve"
        if choice in ("r", "reject"):
            return "reject"
        if choice in ("d", "defer"):
            return "defer"
        print("  Please enter A, R, or D.")


# ---------------------------------------------------------------------------
# Core command handlers
# ---------------------------------------------------------------------------


def cmd_decide(args: argparse.Namespace) -> int:
    # Import here to keep startup fast when --help is used
    import genesis_architect_pro.gde_engine_registration  # noqa: F401 — registers engines
    from genesis_architect_pro import GenesisDecisionEngine
    from genesis_architect_pro.gde_types import ApprovalChoice, ApprovalDecision, GateOutcome

    project_dir = Path(args.dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"  error: --dir '{project_dir}' is not a directory", file=sys.stderr)
        return 1

    print()
    print(f"  Genesis Decision Engine — v6.1.0")
    print(f"  Project: {project_dir}")
    print(f"  Input:   {args.instruction!r}")
    print()

    gde = GenesisDecisionEngine(project_dir=project_dir, parallel=not args.serial)

    # Classify-only mode — no execution
    if args.classify_only:
        intent = gde.classify_intent(args.instruction)
        print(f"  Mode:       {intent.mode.value}")
        print(f"  Confidence: {intent.confidence:.2f}")
        print(f"  Signals:    {intent.signals}")
        if intent.clarifying_questions:
            print()
            print("  Clarifying questions:")
            for q in intent.clarifying_questions:
                print(f"    ? {q}")
        return 0

    # Full session
    report = gde.run(args.instruction, resume=args.resume)
    _print_report_summary(report)

    # HARD_BLOCK → exit immediately
    if report.gate_report.overall == GateOutcome.HARD_BLOCK:
        print("  Session blocked — no writes executed.", file=sys.stderr)
        return 2

    # APPROVE stage: prompt if there are pending writes or soft blocks
    has_pending = bool(
        report.gate_report.blocks or report.engine_results
    )

    if has_pending and not args.yes and not args.no_commit:
        request = gde.approve(report)
        raw_choice = _prompt_approval(request)
        choice_map = {
            "approve": ApprovalChoice.APPROVE,
            "reject": ApprovalChoice.REJECT,
            "defer": ApprovalChoice.DEFER,
        }
        decision = ApprovalDecision(
            session_id=report.session_id,
            choice=choice_map[raw_choice],
        )
    elif args.yes and not args.no_commit:
        decision = ApprovalDecision(
            session_id=report.session_id,
            choice=ApprovalChoice.APPROVE,
        )
    else:
        return 0

    # COMMIT stage
    result = gde.commit(report, decision)

    print()
    if result.success:
        committed = len(result.committed)
        print(f"  Committed {committed} write operation(s).")
        if result.rolled_back:
            print(f"  Rolled back: {result.rolled_back}")
    else:
        print("  Commit completed with errors:", file=sys.stderr)
        for err in result.errors:
            print(f"    {err}", file=sys.stderr)
        return 3

    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    """Print the last decision log in human-readable form."""
    from genesis_architect_pro import read_decision_log

    project_dir = Path(args.dir).expanduser().resolve()
    entries = read_decision_log(project_dir)
    if not entries:
        print("  No decision log found.")
        return 0

    print()
    print(f"  Decision log — {len(entries)} entr{'y' if len(entries)==1 else 'ies'}")
    print(_hr())
    for e in entries:
        print(
            f"  [{e.stage.value:8}] {e.decision_type:28} "
            f"conf={e.confidence_after:.2f}  →  {e.outcome}"
        )
    print(_hr())
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="genesis decide",
        description="Genesis Decision Engine — route any instruction to the right engines",
    )
    sub = parser.add_subparsers(dest="command")

    # genesis decide <instruction>
    decide = sub.add_parser("decide", help="Run a full GDE session")
    decide.add_argument("instruction", help="Free-text instruction (e.g. 'diagnose the project')")
    decide.add_argument(
        "--dir", default=".", metavar="PATH",
        help="Project directory (default: current directory)",
    )
    decide.add_argument(
        "--resume", action="store_true",
        help="Resume a saved session instead of starting fresh",
    )
    decide.add_argument(
        "--serial", action="store_true",
        help="Run engines serially instead of in parallel (useful for debugging)",
    )
    decide.add_argument(
        "--classify-only", action="store_true",
        help="Only classify the instruction and print the mode — do not run engines",
    )
    decide.add_argument(
        "--yes", "-y", action="store_true",
        help="Automatically approve all write operations (non-interactive)",
    )
    decide.add_argument(
        "--no-commit", action="store_true",
        help="Skip the APPROVE/COMMIT stage entirely — analysis only",
    )

    # genesis explain
    explain = sub.add_parser("explain", help="Print the last session's decision log")
    explain.add_argument(
        "--dir", default=".", metavar="PATH",
        help="Project directory (default: current directory)",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()

    # Allow bare `genesis decide "..."` without typing the subcommand name
    # when the first argument doesn't match a known subcommand.
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] not in ("decide", "explain", "-h", "--help"):
        argv = ["decide"] + argv

    args = parser.parse_args(argv)

    if args.command == "decide":
        return cmd_decide(args)
    if args.command == "explain":
        return cmd_explain(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
