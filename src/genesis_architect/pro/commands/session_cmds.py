"""GDE session commands — decide, and the wrappers that phrase it for you.

Split out of gde_cli.py verbatim.

`recover` and `harden` are deliberately thin: each expands to a full-sentence
instruction and calls `cmd_decide`, so there is one session pipeline rather
than three that drift apart. `explain` reads back the decision log a previous
session wrote.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from genesis_architect.pro.commands.formatting import (
    _hr,
    _jsonable,
    _print_report_summary,
    _prompt_approval,
    _rich_approval,
    _rich_classify,
    _rich_commit,
    _rich_header,
    _rich_report,
    _use_rich,
)


def cmd_decide(args: argparse.Namespace) -> int:
    from genesis_architect.pro.engine_bootstrap import ensure_registered
    ensure_registered()
    from genesis_architect.pro import GenesisDecisionEngine, __version__
    from genesis_architect.pro.gde_types import ApprovalChoice, ApprovalDecision, GateOutcome

    project_dir = Path(args.dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"  error: --dir '{project_dir}' is not a directory", file=sys.stderr)
        return 1

    json_output = bool(getattr(args, "json_output", False))
    # JSON is for a consumer that pipes the output, and a pipe cannot answer an
    # approval prompt. Rather than hang on one, --json runs analysis-only: the
    # report is emitted in full and no write is attempted.
    if json_output:
        args.no_commit = True

    rich = _use_rich() and not json_output

    if rich:
        _rich_header(__version__, project_dir, args.instruction)
    elif not json_output:
        print()
        print(f"  Genesis Decision Engine  v{__version__}")
        print(f"  Project: {project_dir}")
        print(f"  Input:   {args.instruction!r}")
        print()

    gde = GenesisDecisionEngine(project_dir=project_dir, parallel=not args.serial)

    # Classify-only mode
    if args.classify_only:
        intent = gde.classify_intent(args.instruction)
        if json_output:
            import json as _json
            print(_json.dumps({
                "version": __version__,
                "project": str(project_dir),
                "instruction": args.instruction,
                "intent": _jsonable(intent),
            }, indent=2))
            return 0
        if rich:
            _rich_classify(intent)
        else:
            print(f"  Mode:       {intent.mode.value}")
            print(f"  Confidence: {intent.confidence:.2f}")
            print(f"  Signals:    {intent.signals}")
            if intent.clarifying_questions:
                print()
                for q in intent.clarifying_questions:
                    print(f"    ? {q}")
        return 0

    # Full session — show spinner if rich available
    if rich:
        from rich.console import Console
        from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

        console = Console()
        with Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[dim]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Running engines...", total=None)
            report = gde.run(args.instruction, resume=args.resume)
            progress.update(task, description="Done")

        _rich_report(report)
    else:
        report = gde.run(args.instruction, resume=args.resume)
        if json_output:
            import json as _json
            print(_json.dumps({
                "version": __version__,
                "project": str(project_dir),
                "instruction": args.instruction,
                "committed": False,   # --json is analysis-only, see above
                "report": _jsonable(report),
            }, indent=2))
            return 2 if report.gate_report.overall == GateOutcome.HARD_BLOCK else 0
        _print_report_summary(report)

    # HARD_BLOCK
    if report.gate_report.overall == GateOutcome.HARD_BLOCK:
        if rich:
            from rich.console import Console
            Console().print("\n  [bold red]Session blocked[/bold red] — no writes executed.")
        else:
            print("  Session blocked — no writes executed.", file=sys.stderr)
        return 2

    # APPROVE stage
    has_pending = bool(report.gate_report.blocks or report.engine_results)

    if has_pending and not args.yes and not args.no_commit:
        request = gde.approve(report)
        raw_choice = _rich_approval(request) if rich else _prompt_approval(request)
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

    if rich:
        return _rich_commit(result)

    print()
    if result.success:
        print(f"  Committed {len(result.committed)} write operation(s).")
        if result.rolled_back:
            print(f"  Rolled back: {result.rolled_back}")
    else:
        print("  Commit failed:", file=sys.stderr)
        for err in result.errors:
            print(f"    {err}", file=sys.stderr)
        return 3

    return 0
def cmd_explain(args: argparse.Namespace) -> int:
    """Print the last decision log in human-readable form."""
    from genesis_architect.pro import read_decision_log

    project_dir = Path(args.dir).expanduser().resolve()
    entries = read_decision_log(project_dir)

    if getattr(args, "json_output", False):
        import json as _json
        print(_json.dumps({
            "project": str(project_dir),
            "entry_count": len(entries),
            "entries": _jsonable(entries),
        }, indent=2))
        return 0

    if _use_rich():
        from rich.console import Console
        from rich.table import Table
        from rich import box

        console = Console()
        console.print()
        if not entries:
            console.print("  [dim]No decision log found.[/dim]")
            return 0

        table = Table(title=f"Decision Log — {len(entries)} entries",
                      box=box.SIMPLE, show_header=True, header_style="dim",
                      border_style="bright_black", padding=(0, 2))
        table.add_column("Stage", style="dim", width=12)
        table.add_column("Decision", style="white")
        table.add_column("Conf", width=6)
        table.add_column("Outcome", style="dim")

        for e in entries:
            conf_str = f"{e.confidence_after:.0%}" if e.confidence_after is not None else "—"
            table.add_row(e.stage.value, e.decision_type, conf_str, str(e.outcome))
        console.print(table)
        console.print()
    else:
        if not entries:
            print("  No decision log found.")
            return 0
        print()
        print(f"  Decision log — {len(entries)} entr{'y' if len(entries)==1 else 'ies'}")
        print(_hr())
        for e in entries:
            print(
                f"  [{e.stage.value:8}] {e.decision_type:28} "
                f"conf={e.confidence_after:.2f}  ->  {e.outcome}"
            )
        print(_hr())

    return 0
def cmd_recover(args: argparse.Namespace) -> int:
    """`genesis recover [PATH]` — thin wrapper: expands to a full-sentence
    RECOVERY-mode instruction and delegates to cmd_decide. A single bare word
    like "recover" scores too low to classify reliably (see intent_classifier
    signal weights); a full sentence routes deterministically."""
    decide_args = argparse.Namespace(
        instruction=(
            "diagnose the project's health: identify drift, broken imports, "
            "anti-patterns, and architecture decay"
        ),
        dir=args.path,
        resume=args.resume,
        serial=args.serial,
        classify_only=args.classify_only,
        yes=args.yes,
        no_commit=args.no_commit,
        json_output=getattr(args, "json_output", False),
    )
    return cmd_decide(decide_args)
def cmd_harden(args: argparse.Namespace) -> int:
    """`genesis harden [PATH]` — thin wrapper: expands to a full-sentence
    GATE-mode instruction (STRIDE + OWASP + secrets scan via the
    security_templates engine) and delegates to cmd_decide."""
    decide_args = argparse.Namespace(
        instruction=(
            "run a security gate check: STRIDE threat model, OWASP Top 10 "
            "checklist, secrets scan, and compliance validation"
        ),
        dir=args.path,
        resume=args.resume,
        serial=args.serial,
        classify_only=args.classify_only,
        yes=args.yes,
        no_commit=args.no_commit,
        json_output=getattr(args, "json_output", False),
    )
    return cmd_decide(decide_args)
