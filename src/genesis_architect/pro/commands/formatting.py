"""Shared CLI presentation — Rich output, plain-text fallbacks, prompts.

Split out of gde_cli.py verbatim. These are used by handlers in every command
group, which is what makes them shared rather than belonging to any one of
them.

Rich is optional: `_use_rich()` reports whether it is importable, and every
helper here has a plain-text counterpart so the CLI degrades to something
readable rather than failing when it is absent.
"""

from __future__ import annotations

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
        table.add_row("Signals", ", ".join(s.replace("\\b", "") for s in intent.signals[:4]))
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
    summary.append("  Session   ", style="dim")
    summary.append(report.session_id[:12] + "…\n", style="white")
    summary.append("  Mode      ", style="dim")
    summary.append(report.mode.value + "\n", style="bold cyan")
    summary.append("  Stage     ", style="dim")
    summary.append(report.stage.value + "\n", style="white")
    summary.append("  Confidence", style="dim")
    summary.append(f"  {conf:.0%}\n", style=conf_style)
    summary.append("  Risk      ", style="dim")
    summary.append(str(report.project_risk_level) + "\n", style="white")
    summary.append("  Gate      ", style="dim")
    summary.append(gate, style=gate_style)

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
            # An engine that did not cleanly succeed is exactly when its known
            # failure modes are worth reading: they say whether this result is
            # a documented way of being wrong or something new.
            for mode in _failure_modes_for(eid, r):
                print(f"              known mode: {mode}")

    n = len(report.decision_log)
    print()
    print(f"  Decision log: {n} entr{'y' if n == 1 else 'ies'}")
    print(_hr())


def _failure_modes_for(engine_id: str, result) -> list[str]:
    """Declared failure modes for an engine, but only when it did not cleanly
    succeed. Printing them on every success would train the reader to skip
    them, which costs exactly the attention they exist to buy.
    """
    status = getattr(getattr(result, "status", None), "value", "")
    if status == "success":
        return []
    try:
        from genesis_architect.pro.engine_registry import get_default_registry

        desc = get_default_registry().get(engine_id)
    except Exception:  # noqa: BLE001 — reporting must never break the report
        return []
    return list(desc.failure_modes) if desc is not None else []


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

def _jsonable(value):
    """Recursively convert a GDE dataclass tree into JSON-safe primitives."""
    import dataclasses
    from enum import Enum
    from pathlib import Path as _Path

    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, _Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
