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
# Rich TUI helpers
# ---------------------------------------------------------------------------

def _use_rich() -> bool:
    """Return True if rich is available and stdout is a real terminal."""
    try:
        import rich  # noqa: F401
        return True
    except ImportError:
        return False


def _rich_header(version: str, project_dir: Path, instruction: str) -> None:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich import box

    console = Console()
    console.print()
    title = Text()
    title.append("Genesis Decision Engine ", style="bold white")
    title.append(f"v{version}", style="dim cyan")
    body = Text()
    body.append("  Project  ", style="dim")
    body.append(str(project_dir), style="cyan")
    body.append("\n  Input    ", style="dim")
    body.append(repr(instruction), style="bold white")
    console.print(Panel(body, title=title, border_style="bright_black", box=box.ROUNDED, padding=(0, 1)))
    console.print()


def _rich_classify(intent) -> None:
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("key", style="dim", width=14)
    table.add_column("val", style="bold white")

    conf = intent.confidence
    conf_color = "green" if conf >= 0.5 else ("yellow" if conf >= 0.3 else "red")
    mode_colors = {
        "recovery": "magenta", "research": "cyan", "refactor": "blue",
        "gate": "yellow", "build": "green", "document": "white", "committee": "purple",
    }
    mode_style = f"bold {mode_colors.get(intent.mode.value, 'white')}"

    table.add_row("Mode", f"[{mode_style}]{intent.mode.value}[/{mode_style}]")
    table.add_row("Confidence", f"[{conf_color}]{conf:.0%}[/{conf_color}]")
    if intent.signals:
        table.add_row("Signals", ", ".join(s.strip("\\b") for s in intent.signals[:4]))
    console.print(table)

    if intent.clarifying_questions:
        console.print()
        for q in intent.clarifying_questions:
            console.print(f"  [dim]?[/dim]  {q}")
    console.print()


def _rich_report(report) -> None:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box

    console = Console()

    gate = report.gate_report.overall.value.upper()
    gate_style = {"PASS": "bold green", "WARN": "bold yellow",
                  "BLOCK": "bold yellow", "HARD_BLOCK": "bold red"}.get(gate, "white")

    conf = report.overall_confidence
    conf_style = "green" if conf >= 0.7 else ("yellow" if conf >= 0.4 else "red")

    # Summary panel
    summary = Text()
    summary.append("  Session   ", style="dim"); summary.append(report.session_id[:12] + "…\n", style="white")
    summary.append("  Mode      ", style="dim"); summary.append(report.mode.value + "\n", style="bold cyan")
    summary.append("  Stage     ", style="dim"); summary.append(report.stage.value + "\n", style="white")
    summary.append("  Confidence", style="dim"); summary.append(f"  {conf:.0%}\n", style=conf_style)
    summary.append("  Risk      ", style="dim"); summary.append(str(report.project_risk_level) + "\n", style="white")
    summary.append("  Gate      ", style="dim"); summary.append(gate, style=gate_style)

    console.print(Panel(summary, title="[bold]Session Report[/bold]", border_style="bright_black",
                        box=box.ROUNDED, padding=(0, 1)))

    # Gate issues
    if report.gate_report.hard_blocks:
        console.print()
        for g in report.gate_report.hard_blocks:
            console.print(f"  [bold red]HARD BLOCK[/bold red]  [{g.gate_id}]  {g.reason}")
    if report.gate_report.blocks:
        for g in report.gate_report.blocks:
            console.print(f"  [bold yellow]BLOCK[/bold yellow]       [{g.gate_id}]  {g.reason}")
    if report.gate_report.warnings:
        for g in report.gate_report.warnings:
            console.print(f"  [dim yellow]WARN[/dim yellow]        [{g.gate_id}]  {g.reason}")

    # Engine results
    if report.engine_results:
        console.print()
        table = Table(box=box.SIMPLE, show_header=True, padding=(0, 2),
                      header_style="dim", border_style="bright_black")
        table.add_column("Engine", style="white")
        table.add_column("Status", width=10)
        table.add_column("Conf", width=6)
        table.add_column("Warnings")

        status_styles = {
            "SUCCESS": "bold green", "DEGRADED": "bold yellow",
            "FAILED": "bold red", "SKIPPED": "dim",
        }
        for eid, r in report.engine_results.items():
            st = r.status.value
            st_style = status_styles.get(st, "white")
            conf_str = f"{r.confidence:.0%}" if hasattr(r, "confidence") and r.confidence is not None else "—"
            warns = "; ".join(r.warnings[:2]) if hasattr(r, "warnings") and r.warnings else ""
            table.add_row(eid, f"[{st_style}]{st}[/{st_style}]", conf_str,
                          f"[dim yellow]{warns}[/dim yellow]" if warns else "")
        console.print(table)

    n = len(report.decision_log)
    console.print(f"\n  [dim]Decision log:[/dim] {n} entr{'y' if n == 1 else 'ies'}")
    console.print()


def _rich_approval(request) -> str:
    """Rich interactive approval prompt. Returns 'approve', 'reject', or 'defer'."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    from rich.prompt import Prompt

    console = Console()
    console.print()

    body = Text()
    body.append(request.summary + "\n\n", style="white")
    if request.pending_writes:
        body.append(f"  {len(request.pending_writes)} pending write operation(s):\n", style="dim")
        for op in request.pending_writes:
            rev = "[yellow]IRREVERSIBLE[/yellow]" if not op.is_reversible else "[dim]reversible[/dim]"
            body.append(f"    {op.target_path}", style="cyan")
            body.append(f"  —  {op.description}\n", style="dim")
    else:
        body.append("  No write operations pending.\n", style="dim")

    console.print(Panel(body, title="[bold yellow]Approval Required[/bold yellow]",
                        border_style="yellow", box=box.ROUNDED, padding=(0, 1)))
    console.print()
    console.print("  [green]\\[A\\]pprove[/green]   [red]\\[R\\]eject[/red]   [dim]\\[D\\]efer[/dim]")

    while True:
        try:
            choice = Prompt.ask("  Choice", console=console, default="D").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return "defer"
        if choice in ("a", "approve"):
            return "approve"
        if choice in ("r", "reject"):
            return "reject"
        if choice in ("d", "defer"):
            return "defer"
        console.print("  [dim]Please enter A, R, or D.[/dim]")


def _rich_commit(result) -> int:
    from rich.console import Console
    console = Console()
    console.print()
    if result.success:
        n = len(result.committed)
        console.print(f"  [bold green]Committed[/bold green] {n} write operation(s).")
        if result.rolled_back:
            console.print(f"  [yellow]Rolled back:[/yellow] {result.rolled_back}")
        return 0
    else:
        console.print("  [bold red]Commit failed:[/bold red]", file=sys.stderr)
        for err in result.errors:
            console.print(f"    [red]{err}[/red]", file=sys.stderr)
        return 3


# ---------------------------------------------------------------------------
# Fallback plain-text helpers (no rich)
# ---------------------------------------------------------------------------

def _hr(char: str = "-", width: int = 60) -> str:
    return char * width


def _print_report_summary(report) -> None:
    gate_label = report.gate_report.overall.value.upper()
    gate_color = {
        "PASS": "\033[32m", "WARN": "\033[33m",
        "BLOCK": "\033[33m", "HARD_BLOCK": "\033[31m",
    }.get(gate_label, "")
    reset = "\033[0m"

    print(_hr())
    print(f"  Session:    {report.session_id[:12]}...")
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
        print("  BLOCKS:")
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

    n = len(report.decision_log)
    print()
    print(f"  Decision log: {n} entr{'y' if n == 1 else 'ies'}")
    print(_hr())


def _prompt_approval(request) -> str:
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
            print(f"    [{rev}] {op.target_path}  -  {op.description}")
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
    import genesis_architect_pro.gde_engine_registration  # noqa: F401
    from genesis_architect_pro import GenesisDecisionEngine, __version__
    from genesis_architect_pro.gde_types import ApprovalChoice, ApprovalDecision, GateOutcome

    project_dir = Path(args.dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"  error: --dir '{project_dir}' is not a directory", file=sys.stderr)
        return 1

    rich = _use_rich()

    if rich:
        _rich_header(__version__, project_dir, args.instruction)
    else:
        print()
        print(f"  Genesis Decision Engine  v{__version__}")
        print(f"  Project: {project_dir}")
        print(f"  Input:   {args.instruction!r}")
        print()

    gde = GenesisDecisionEngine(project_dir=project_dir, parallel=not args.serial)

    # Classify-only mode
    if args.classify_only:
        intent = gde.classify_intent(args.instruction)
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
    from genesis_architect_pro import read_decision_log

    project_dir = Path(args.dir).expanduser().resolve()
    entries = read_decision_log(project_dir)

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


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="genesis decide",
        description="Genesis Decision Engine — route any instruction to the right engines",
    )
    sub = parser.add_subparsers(dest="command")

    decide = sub.add_parser("decide", help="Run a full GDE session")
    decide.add_argument("instruction", help="Free-text instruction (e.g. 'diagnose the project')")
    decide.add_argument("--dir", default=".", metavar="PATH",
                        help="Project directory (default: current directory)")
    decide.add_argument("--resume", action="store_true",
                        help="Resume a saved session instead of starting fresh")
    decide.add_argument("--serial", action="store_true",
                        help="Run engines serially (useful for debugging)")
    decide.add_argument("--classify-only", action="store_true",
                        help="Only classify the instruction — do not run engines")
    decide.add_argument("--yes", "-y", action="store_true",
                        help="Auto-approve all write operations (CI mode)")
    decide.add_argument("--no-commit", action="store_true",
                        help="Skip APPROVE/COMMIT — analysis only")

    explain = sub.add_parser("explain", help="Print the last session's decision log")
    explain.add_argument("--dir", default=".", metavar="PATH",
                         help="Project directory (default: current directory)")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()

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
