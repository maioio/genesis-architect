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
import threading
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
        from genesis_architect_pro.engine_registry import get_default_registry

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


# ---------------------------------------------------------------------------
# Core command handlers
# ---------------------------------------------------------------------------


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


def cmd_decide(args: argparse.Namespace) -> int:
    import genesis_architect_pro.gde_engine_registration  # noqa: F401
    from genesis_architect_pro import GenesisDecisionEngine, __version__
    from genesis_architect_pro.gde_types import ApprovalChoice, ApprovalDecision, GateOutcome

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


def cmd_memory(args: argparse.Namespace) -> int:
    """Show or update the per-project memory under .genesis/."""
    from genesis_architect_pro.memory_engine import (
        memory_status, init_memory, read_memory,
    )

    project_dir = Path(args.dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"  error: --dir '{project_dir}' is not a directory", file=sys.stderr)
        return 1

    if args.init:
        init_memory(project_dir)
        print(f"  Memory initialised at {project_dir / '.genesis'}")
        return 0

    if getattr(args, "sessions", False):
        return _cmd_memory_sessions(project_dir, args)

    if args.status:
        status = memory_status(project_dir)
        if _use_rich():
            from rich.console import Console
            from rich.table import Table
            from rich import box
            console = Console()
            console.print()
            table = Table(title="Project Memory Status", box=box.SIMPLE,
                          header_style="dim", border_style="bright_black", padding=(0, 2))
            table.add_column("File")
            table.add_column("Exists")
            table.add_column("Size")
            for fname, count in status.items():
                exists = "[green]yes[/green]" if count is not False else "[dim]no[/dim]"
                size = f"{count} lines" if count is not False else "—"
                table.add_row(fname, exists, size)
            console.print(table)
            console.print()
        else:
            print()
            print("  Project Memory Status")
            print(_hr())
            for fname, count in status.items():
                exists = "yes" if count is not False else "no"
                size = f"{count} lines" if count is not False else "—"
                print(f"  {exists:3}  {size:12}  {fname}")
            print(_hr())
        return 0

    # Default: show all memory files
    mem = read_memory(project_dir)
    if not mem:
        print("  No memory files found. Run `genesis memory --init` to create them.")
        return 0
    for fname, content in mem.items():
        print(f"\n--- {fname} ---")
        lines = content.splitlines()
        for line in lines[:20]:
            print(f"  {line}")
        if len(lines) > 20:
            print(f"  ... ({len(lines) - 20} more lines)")
    return 0


def _cmd_memory_sessions(project_dir: Path, args: argparse.Namespace) -> int:
    """`genesis memory --sessions` — the cross-session memory door.

    `genesis memory` shows the .genesis/*.md files; cross-session memory is a
    different thing entirely (the restorable research/build context), and it
    had no command at all. Sharing the `memory` noun keeps the two where a
    reader will look for them, separated by an explicit flag.
    """
    from genesis_architect_pro.cross_session_memory import (
        list_analyzed_videos, no_session_message, restore_session,
    )

    context = restore_session(project_dir)
    videos = list_analyzed_videos(project_dir)

    if getattr(args, "json_output", False):
        import json as _json
        print(_json.dumps({
            "restored": context.restored,
            "context": context.__dict__,
            "age_hours": round(context.age_hours(), 2) if context.restored else None,
            "announcement": context.announce(),
            "analyzed_videos": videos,
        }, indent=2, default=str))
        return 0

    print()
    if not context.restored:
        print(f"  {no_session_message()}")
        print()
        return 0

    print("  Cross-Session Memory")
    print(_hr())
    print(f"  {context.announce()}")
    print()
    print(f"  Vision           {context.vision}")
    print(f"  Last phase       {context.last_phase}")
    print(f"  Research quality {context.research_quality}")
    print(f"  Repos            {context.repo_count} ({context.deep_count} deep-analyzed)")
    print(f"  Pitfalls         {context.pitfall_count}")
    print(f"  Vault cache      {'hit' if context.vault_hit else 'miss'}")
    if videos:
        print(f"  Videos absorbed  {len(videos)}")
        for url in videos[:5]:
            print(f"                   {url}")
    print(_hr())
    print()
    return 0


def cmd_engines(args: argparse.Namespace) -> int:
    """`genesis engines` — the capability map: every engine and its command.

    Exists because an engine nobody can find is an engine nobody has. See
    capability_map for the drift guard that keeps this list honest.
    """
    from genesis_architect_pro.capability_map import format_map, to_dict

    if getattr(args, "json_output", False):
        import json as _json
        print(_json.dumps(to_dict(), indent=2))
        return 0

    print(format_map(show_modules=getattr(args, "modules", False)))
    return 0


def cmd_deps(args: argparse.Namespace) -> int:
    """`genesis deps [PATH]` — dependency and package-health door.

    Wraps two engines that previously had no command of their own: the
    dependency scanner (third-party imports per module, plus their CVEs) and
    the package registry (release recency and advisories from PyPI, npm,
    crates.io, Maven, NuGet and OSV).
    """
    from genesis_architect_pro.dependency_scanner import (
        find_python_dependencies, scan_dependency_cves,
    )

    project_dir = Path(getattr(args, "path", ".")).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"\n  Not a directory: {project_dir}\n", file=sys.stderr)
        return 1

    # --- single-package lookup: registry only, no project scan needed ---
    requested = getattr(args, "package", None)
    if requested:
        from genesis_architect_pro.package_registry import query_package

        ecosystem = getattr(args, "ecosystem", None) or "pypi"
        signal = query_package(requested, ecosystem)
        if getattr(args, "json_output", False):
            import json as _json
            print(_json.dumps(signal.__dict__, indent=2, default=str))
            return 0
        print()
        print(f"  {requested} ({ecosystem})")
        print(_hr())
        for key, value in signal.__dict__.items():
            print(f"  {key:18} {value}")
        print(_hr())
        print()
        return 0

    deps = find_python_dependencies(project_dir)
    cves = scan_dependency_cves(project_dir) if deps and not getattr(args, "no_cve", False) else []

    packages: dict[str, list[str]] = {}
    for module, names in deps.items():
        for name in names:
            packages.setdefault(name, []).append(module)

    if getattr(args, "json_output", False):
        import json as _json
        print(_json.dumps({
            "project": str(project_dir),
            "packages": {name: sorted(mods) for name, mods in sorted(packages.items())},
            "modules_scanned": len(deps),
            "cves": cves,
            "cve_scan_ran": bool(deps) and not getattr(args, "no_cve", False),
        }, indent=2, default=str))
        return 0

    print()
    if not deps:
        # Say which case this is. "0 dependencies" and "this scanner only
        # speaks Python" look identical in the output otherwise.
        print(f"  No third-party Python imports found under {project_dir}.")
        print("  (This scanner covers Python projects; other ecosystems are not "
              "scanned yet.)")
        print()
        return 0

    print(f"  Dependencies — {project_dir}")
    print(_hr())
    print(f"  {len(packages)} third-party package(s) across {len(deps)} module(s)")
    print()
    for name, mods in sorted(packages.items()):
        print(f"  {name:<28} {len(mods)} module(s)")
    print()

    if cves:
        print(f"  {len(cves)} advisory/ies found")
        print()
        for cve in cves:
            print(f"  {cve['id']:<22} {cve['package']}")
            print(f"  {'':22} in {', '.join(cve['modules'][:3])}")
        print()
    elif not getattr(args, "no_cve", False):
        print("  No advisories found for the scanned packages.")
        print()
    print(_hr())
    print()
    return 0 if not cves else 1


def cmd_ui(args: argparse.Namespace) -> int:
    """Generate (or open) the self-contained HTML workspace."""
    from genesis_architect_pro.ui_workspace import write_workspace

    project_dir = Path(args.dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"  error: --dir '{project_dir}' is not a directory", file=sys.stderr)
        return 1

    out_name = Path(args.output).name if args.output else "workspace.html"
    written = write_workspace(project_dir, out_name)

    if written is None:
        print(f"  error: could not write the workspace under {project_dir / '.genesis' / 'ui'}", file=sys.stderr)
        return 1

    if _use_rich():
        from rich.console import Console
        Console().print(
            f"\n  [bold green]Workspace written:[/bold green] {written}\n"
            f"  [dim]Open in any browser — no server required.[/dim]\n"
        )
    else:
        print(f"\n  Workspace written: {written}")
        print("  Open in any browser — no server required.\n")

    if args.open:
        import webbrowser
        webbrowser.open(str(written))

    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    """Print the last decision log in human-readable form."""
    from genesis_architect_pro import read_decision_log

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


def _companion_check() -> int:
    """Report voice readiness (STT/TTS) without downloading anything."""
    from genesis_architect_pro.voice import readiness

    r = readiness()
    print()
    print("  Voice readiness")
    print(_hr())
    for c in r.components:
        mark = "OK " if c.ready else "-- "
        line = f"  {mark} {c.name:14} {c.detail}"
        print(line)
        if not c.ready and c.fix:
            print(f"       fix: {c.fix}")
    print(_hr())
    if r.end_to_end_ready:
        print("  Voice is READY end-to-end (STT + a real TTS voice).")
    else:
        print("  Voice is NOT ready end-to-end.")
        print("  Run `genesis companion --setup` after installing the [voice] extra.")
    print()
    return 0 if r.end_to_end_ready else 1


def _companion_setup() -> int:
    """Download STT/TTS models, then print readiness."""
    from genesis_architect_pro.voice import run_setup, readiness

    print("\n  Setting up Genesis voice models (local, no cloud)…\n")
    result = run_setup()
    for step in result.steps:
        print(f"    {step}")
    for d in result.downloaded:
        print(f"  [+] {d}")
    for s in result.skipped:
        print(f"  [=] {s}")
    for f in result.failed:
        print(f"  [!] {f}")

    print()
    r = readiness()
    if r.end_to_end_ready:
        print("  Voice is now READY end-to-end. Try: genesis companion --speak \"שלום\"")
        print()
        return 0
    print("  Voice is still NOT ready end-to-end. Remaining gaps:")
    for c in r.components:
        if not c.ready and c.name != "fallback" and c.fix:
            print(f"    - {c.name}: {c.fix}")
    print()
    return 1


def _companion_speak(text: str) -> int:
    """Speak a phrase to verify the TTS round-trip. Reports honestly if unavailable."""
    from genesis_architect_pro.voice import TTSPipeline, Urgency, detect_lang, readiness

    r = readiness()
    lang = detect_lang(text)
    real_voice = r.tts_hebrew_ready if lang == "he" else r.tts_english_ready
    if not real_voice and not r.fallback_ready:
        print(f"\n  Cannot speak: no TTS engine available for '{lang}'.")
        print("  Run `genesis companion --setup` (and install the [voice] extra).\n")
        return 1

    engine = "real model" if real_voice else "eSpeak fallback"
    print(f"\n  Speaking ({lang}, {engine}): {text}\n")
    TTSPipeline().speak(text, urgency=Urgency.CRITICAL)  # sync so we hear it before exit
    return 0


def cmd_companion_serve(project_dir: Path) -> int:
    """Start the full Companion backend (WebSocket + IDE bridge) for Tauri.

    Prints READY token=<64-hex-chars> to stdout, then blocks until killed.
    Handles SIGTERM and SIGINT for graceful shutdown.
    """
    import signal

    import socket

    from genesis_architect_pro.gde_companion import GateNotifier
    from genesis_architect_pro.streaming.server import CompanionServer
    from genesis_architect_pro.ide_bridge.server import IDEBridgeServer
    from genesis_architect_pro.streaming import runner_patch
    from genesis_architect_pro import gate_notifier_patch
    from genesis_architect_pro.streaming.inbound import InboundRouter
    from genesis_architect_pro.streaming.events import default_emitter

    # 0. Fail fast if the WebSocket port is already held by a stale backend.
    #    Otherwise websockets.serve() raises inside the daemon thread, no READY
    #    line is ever printed, and the Tauri shell hangs 15s then connects to
    #    the *stale* server with a mismatched token — the UI sticks on
    #    "connecting". A clear stderr line lets the shell surface the problem.
    _probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _in_use = _probe.connect_ex(("127.0.0.1", 47291)) == 0
    finally:
        _probe.close()
    if _in_use:
        print(
            "ERROR: port 47291 is already in use — another Genesis Companion "
            "backend is running. Close it and relaunch.",
            file=sys.stderr,
        )
        return 3

    # 1. Start WebSocket server
    ws_server = CompanionServer(emitter=default_emitter)
    ws_server.start_in_background()

    # 2. Install GDE runner streaming patch
    runner_patch.install()

    # 3. Start IDE Bridge
    ide_bridge = IDEBridgeServer()
    ide_bridge.start()

    # 4. Wire GateNotifier
    project_name = project_dir.name or "Genesis"
    notifier = GateNotifier(project_name=project_name)
    gate_notifier_patch.install(notifier)

    # 5. Build InboundRouter, wire IDE bridge, register as on_message callback
    router = InboundRouter(
        project_dir=project_dir,
        emitter=default_emitter,
        ide_bridge=ide_bridge,
    )

    # Patch the server's on_message after construction (server.py stores it at init time)
    # We reassign the internal attribute directly since CompanionServer exposes no setter.
    ws_server._on_message = router.handle  # type: ignore[attr-defined]

    # 6. Print READY line so Tauri can extract the token
    token = ws_server.token
    sys.stdout.write(f"READY token={token}\n")
    sys.stdout.flush()

    # 7. Graceful shutdown handler
    _shutdown = threading.Event()

    def _handle_signal(signum, frame):  # noqa: ANN001
        _shutdown.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Block until killed
    _shutdown.wait()

    # Tear down in reverse order
    runner_patch.uninstall()
    gate_notifier_patch.uninstall()
    ide_bridge.stop()
    ws_server.stop()

    return 0


def cmd_companion_listen(project_dir: Path) -> int:
    """Listen for the wake word and print recognized instructions. Honest about
    readiness: if the mic or STT model is missing, it says exactly what to do."""
    import time

    from genesis_architect_pro.voice.listener import WakeWordListener, mic_status

    mic = mic_status()
    print("\n  Genesis voice listener")
    print(f"  Microphone: {'ready — ' + mic.detail if mic.available else 'NOT ready — ' + mic.detail}")
    if not mic.available:
        print("  Install the voice extra: pip install genesis-architect-pro[voice]\n")
        return 1

    def _on(instruction: str) -> None:
        print(f'\n  ▶ heard: "{instruction}"')

    listener = WakeWordListener(on_instruction=_on)
    if not listener.start():
        print(f"  Cannot listen: {listener.last_error}")
        print("  Run `genesis companion --setup` to download the speech model.\n")
        return 1

    print('  Listening… say "genesis <your request>" (or "ג\'נסיס …"). Ctrl+C to stop.\n')
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        listener.stop()
        print("\n  Stopped.")
    return 0


def _auto_setup_voice() -> None:
    """Make voice fully ready on first launch: install any missing Companion
    packages into this environment, then download the STT/TTS models.

    This is the premium one-command experience — a customer installs
    `genesis-architect-pro` and the first `genesis companion --ui` provisions
    everything else automatically. Shows progress; never raises.
    """
    # setup.py is import-safe with nothing extra installed — import it directly
    # (the voice package __init__ pulls modules that need the extras).
    from genesis_architect_pro.voice.setup import (
        ensure_companion_packages,
        missing_companion_packages,
        readiness,
        run_setup,
    )

    # Step 1 — packages. pip-install whatever is missing, right here.
    if missing_companion_packages():
        print("\n  First launch: installing Companion packages (one-time)…")
        prov = ensure_companion_packages(progress=lambda m: print(f"  {m}"))
        for req in prov.installed:
            print(f"  + {req}")
        for fail in prov.failed:
            print(f"  ! {fail}")
        if prov.failed:
            print("  Voice will run degraded until the packages above install.\n")

    r = readiness()
    if r.end_to_end_ready:
        return  # already ready — nothing to do

    # Step 2 — models. Only when the packages for them are importable.
    needs_download = [
        c for c in r.components
        if not c.ready and c.name != "fallback"
        and c.fix.startswith("genesis companion")
    ]
    if not needs_download:
        return  # remaining gaps are package installs that just failed — reported above

    rich = _use_rich()
    if rich:
        from rich.console import Console
        from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
        console = Console()
        console.print("\n  [bold cyan]First launch:[/bold cyan] downloading voice models (one-time, ~1–2 GB)…")
        with Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[dim]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task("Downloading STT + TTS models…", total=None)
            result = run_setup()
            progress.update(task, description="Done", completed=1, total=1)

        for d in result.downloaded:
            console.print(f"  [green]+[/green] {d}")
        for s in result.skipped:
            console.print(f"  [dim]=[/dim] {s}")
        for f in result.failed:
            console.print(f"  [red]![/red] {f}")
        console.print()
    else:
        print("\n  First launch: downloading voice models (one-time, ~1–2 GB)…")
        result = run_setup()
        for d in result.downloaded:
            print(f"  + {d}")
        for s in result.skipped:
            print(f"  = {s}")
        for f in result.failed:
            print(f"  ! {f}")
        print()


def cmd_companion_ui(project_dir: Path, *, no_browser: bool = False) -> int:
    """Launch the Floating Assistant end-to-end: start the full Companion backend,
    generate the web UI wired to that server's port+token, open it, and block.

    One command → a running floating assistant. Degrades honestly: if the
    streaming server can't start (websockets missing), the UI still opens and
    shows an offline state with the exact install hint.
    """
    import signal
    import time
    import webbrowser

    from genesis_architect_pro.companion_ui import write_companion_html, DEFAULT_PORT

    # Auto-download voice models on first launch if packages are installed but models missing.
    _auto_setup_voice()

    token = ""
    ws_server = None
    try:
        from genesis_architect_pro.gde_companion import GateNotifier
        from genesis_architect_pro.streaming.server import CompanionServer
        from genesis_architect_pro.ide_bridge.server import IDEBridgeServer
        from genesis_architect_pro.streaming import runner_patch
        from genesis_architect_pro import gate_notifier_patch
        from genesis_architect_pro.streaming.inbound import InboundRouter
        from genesis_architect_pro.streaming.events import default_emitter

        ws_server = CompanionServer(emitter=default_emitter)
        ws_server.start_in_background()
        runner_patch.install()
        ide_bridge = IDEBridgeServer()
        ide_bridge.start()
        notifier = GateNotifier(project_name=project_dir.name or "Genesis")
        gate_notifier_patch.install(notifier)
        router = InboundRouter(
            project_dir=project_dir,
            emitter=default_emitter,
            ide_bridge=ide_bridge,
        )
        ws_server._on_message = router.handle  # type: ignore[attr-defined]
        token = ws_server.token
        port = ws_server.port
        print(f"\n  Genesis Companion backend running (ws 127.0.0.1:{port}).")
    except Exception as exc:  # noqa: BLE001
        port = DEFAULT_PORT
        router = None
        print(f"\n  Backend not started ({exc}).")
        print("  Opening the UI in offline mode. For live engines, install:")
        print("    pip install genesis-architect-pro[streaming]\n")

    # Wake word -> the same router the panel's WebSocket uses, so "genesis ..."
    # spoken aloud behaves exactly like typing the instruction into the panel:
    # same GDE pipeline, same engine/gate events streamed back to the open UI.
    # Previously --listen (wake word) and --ui (the panel) were two disconnected
    # commands - you could have one or the other, never both together.
    wake_listener = None
    if ws_server is not None and router is not None:
        try:
            from genesis_architect_pro.streaming.events import MessageType, StreamMessage
            from genesis_architect_pro.voice.listener import WakeWordListener

            def _on_wake_instruction(instruction: str) -> None:
                router.handle(StreamMessage(
                    type=MessageType.USER_INTENT,
                    payload={"instruction": instruction},
                ))

            wake_listener = WakeWordListener(on_instruction=_on_wake_instruction)
            if wake_listener.start():
                print('  Wake word active: say "genesis <request>" (or "ג\'נסיס …").')
            else:
                print(f"  Wake word unavailable: {wake_listener.last_error}")
                wake_listener = None
        except Exception as exc:  # noqa: BLE001
            print(f"  Wake word unavailable: {exc}")
            wake_listener = None

    ui_path = write_companion_html(project_dir, ws_port=port, ws_token=token)
    if ui_path is None:
        print("  error: could not write the UI file.", file=sys.stderr)
        return 1
    print(f"  Floating Assistant: {ui_path}")

    def _shutdown() -> None:
        if wake_listener is not None:
            try:
                wake_listener.stop()
            except Exception:
                pass
        if ws_server is not None:
            try:
                ws_server.stop()
            except Exception:
                pass

    # Prefer a real floating window (frameless, always-on-top, sized to the
    # bubble/panel) over an ordinary browser tab — a browser tab with a URL
    # bar and bookmarks is not the "system-wide floating bubble" the product
    # promises. Falls back to the browser honestly if pywebview (or its
    # native WebView2 runtime) isn't available here.
    if not no_browser:
        from genesis_architect_pro.companion_ui import render_companion_html
        from genesis_architect_pro.companion_window import run_floating_window

        html = render_companion_html(ws_port=port, ws_token=token)
        print("  Opening the floating window. Close it (or Ctrl+C here) to stop.\n")
        started = run_floating_window(html, on_close=_shutdown)
        if started:
            _shutdown()
            print("\n  Companion stopped.")
            return 0
        print("  Native window unavailable — opening in your browser instead.")
        webbrowser.open(ui_path.as_uri())
        print("  Close this terminal (Ctrl+C) to stop.\n")

    if ws_server is None:
        return 0  # offline UI written; nothing to keep alive

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
    except Exception:
        pass
    try:
        while not stop.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    _shutdown()
    print("\n  Companion stopped.")
    return 0


def cmd_companion(args: argparse.Namespace) -> int:
    """Start the health page server or print gate miss-rate stats."""
    from genesis_architect_pro.gde_companion import (
        CompanionInstrumentation,
        HealthPageServer,
    )
    import time

    project_dir = Path(args.dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"  error: --dir '{project_dir}' is not a directory", file=sys.stderr)
        return 1

    # --listen mode: wake-word loop -> print recognized instructions
    if getattr(args, "listen", False):
        return cmd_companion_listen(project_dir)

    # --ui mode: start the backend AND open the Floating Assistant web UI wired to it
    if getattr(args, "ui", False):
        return cmd_companion_ui(project_dir, no_browser=getattr(args, "no_browser", False))

    # --serve mode: full Companion backend for Tauri
    if getattr(args, "serve", False):
        return cmd_companion_serve(project_dir)

    # --setup mode: download voice models, then report readiness
    if getattr(args, "setup", False):
        return _companion_setup()

    # --check mode: report voice readiness without downloading anything
    if getattr(args, "check", False):
        return _companion_check()

    # --speak mode: verify the voice round-trip on a short phrase
    if getattr(args, "speak", None) is not None:
        return _companion_speak(args.speak)

    # --stats mode: print gate miss-rate and exit
    if args.stats:
        stats = CompanionInstrumentation(project_dir).analyse()
        rich = _use_rich()
        if rich:
            from rich.console import Console
            from rich.table import Table
            from rich import box
            console = Console()
            console.print()
            table = Table(title="Gate Miss-Rate Stats", box=box.SIMPLE,
                          header_style="dim", border_style="bright_black", padding=(0, 2))
            table.add_column("Metric")
            table.add_column("Value")
            table.add_row("Sessions analysed", str(stats.sessions_analysed))
            table.add_row("Gates presented", str(stats.total_gates_presented))
            table.add_row("Missed (>5 min)", str(stats.missed_gates))
            miss_style = "red" if stats.miss_rate > 0.15 else "green"
            table.add_row("Miss rate", f"[{miss_style}]{stats.miss_rate:.0%}[/{miss_style}]")
            if stats.avg_response_seconds:
                table.add_row("Avg response time", f"{stats.avg_response_seconds:.0f}s")
            table.add_row(
                "Companion justified?",
                "[green]YES[/green]" if stats.companion_justified else "[dim]not yet[/dim]",
            )
            console.print(table)
            if stats.companion_justified:
                console.print("  [bold green]→ Miss rate >15%. Build the Companion overlay.[/bold green]\n")
            else:
                console.print("  [dim]→ Miss rate ≤15%. CLI + notifications are sufficient.[/dim]\n")
        else:
            print()
            print(f"  Sessions analysed : {stats.sessions_analysed}")
            print(f"  Gates presented   : {stats.total_gates_presented}")
            print(f"  Missed (>5 min)   : {stats.missed_gates}")
            print(f"  Miss rate         : {stats.miss_rate:.0%}")
            if stats.avg_response_seconds:
                print(f"  Avg response time : {stats.avg_response_seconds:.0f}s")
            justified = "YES" if stats.companion_justified else "not yet"
            print(f"  Companion justified: {justified}")
            print()
        return 0

    # Server mode
    server = HealthPageServer(project_dir=project_dir, port=args.port)
    server.start()

    if _use_rich():
        from rich.console import Console
        console = Console()
        console.print(f"\n  [bold]Genesis PRO health page:[/bold] [cyan]{server.url}[/cyan]")
        console.print("  [dim]Press Ctrl-C to stop.[/dim]\n")
    else:
        print(f"\n  Genesis PRO health page: {server.url}")
        print("  Press Ctrl-C to stop.\n")

    if not args.no_browser:
        server.open_browser()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        print("\n  Health page stopped.")

    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """Run the autonomous sync manager (genesis sync)."""
    from genesis_architect_pro.genesis_sync import cli_sync
    return cli_sync(args)


def cmd_doctor(args: argparse.Namespace) -> int:
    """Customer-facing readiness report: license, Pro install, optional deps.

    Deliberately license-exempt (main() skips the license gate for this
    command) — this is the tool you run to find out *why* nothing else works.
    """
    from genesis_architect_pro.first_run import check_readiness, doctor_report

    readiness = check_readiness()
    if getattr(args, "json_output", False):
        import json as _json
        print(_json.dumps({
            "ready_to_work": readiness.ready_to_work,
            "readiness": _jsonable(readiness),
            "report": doctor_report(),
        }, indent=2))
        return 0 if readiness.ready_to_work else 1

    print()
    print(doctor_report())
    print()
    return 0 if readiness.ready_to_work else 1




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


def cmd_advise(args: argparse.Namespace) -> int:
    """`genesis advise` — dual-level MCP & skill recommendations.

    Read-only and non-installing by design: it explains what each tool would
    buy and how Genesis would drive it, then stops. Acting on that is the
    user's decision, not the advisor's.
    """
    from genesis_architect_pro.mcp_advisor import advise, format_report

    project_dir = Path(args.dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"\n  Not a directory: {project_dir}\n", file=sys.stderr)
        return 1

    include_global = not getattr(args, "local_only", False)
    include_local = not getattr(args, "global_only", False)

    report = advise(
        project_dir,
        include_global=include_global,
        include_local=include_local,
    )

    if getattr(args, "json_output", False):
        import json as _json
        print(_json.dumps({
            "signals": {
                "languages": sorted(report.signals.languages),
                "frameworks": sorted(report.signals.frameworks),
                "evidence": report.signals.evidence,
            },
            "local": [r.to_dict() for r in report.local],
            "global": [r.to_dict() for r in report.global_],
            "notes": report.notes,
        }, indent=2))
    else:
        print(format_report(report))
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    """`genesis fetch` — fetch a trusted skill pack into the project sandbox.

    Whitelist-only and read-only: it clones a registered source, marks the
    sandbox ephemeral so Auto-Purge owns its cleanup, reads the skill
    definitions as text, and never executes anything it downloaded.
    """
    from genesis_architect_pro.skill_fetcher import (
        FetchRefused, discard, fetch, format_result, format_sources,
    )

    if getattr(args, "list_sources", False) or not getattr(args, "source_id", None):
        print(format_sources())
        return 0

    project_dir = Path(args.dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"\n  Not a directory: {project_dir}\n", file=sys.stderr)
        return 1

    try:
        if getattr(args, "discard", False):
            removed = discard(args.source_id, project_dir)
            print(f"\n  {'Removed' if removed else 'Nothing to remove for'} "
                  f"{args.source_id}\n")
            return 0
        result = fetch(
            args.source_id, project_dir,
            ttl_hours=getattr(args, "ttl", None) or 2.0,
            force=bool(getattr(args, "force", False)),
        )
    except FetchRefused as exc:
        print(f"\n  {exc}\n", file=sys.stderr)
        return 2

    if getattr(args, "json_output", False):
        import json as _json
        print(_json.dumps(result.to_dict(), indent=2))
    else:
        print(format_result(result))
    return 0 if result.ok else 1


def cmd_purge(args: argparse.Namespace) -> int:
    """`genesis purge [--apply]` — Auto-Purge for expired ephemeral resources.

    Dry run by default: it reports what expired and what it refused to touch,
    and deletes nothing. `--apply` is the only path that removes anything.
    """
    from genesis_architect_pro.ephemeral_purge import (
        DEFAULT_LOCK_TTL_HOURS, DEFAULT_WORKTREE_TTL_HOURS, format_report, purge,
    )

    project_dir = Path(args.dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"\n  Not a directory: {project_dir}\n", file=sys.stderr)
        return 1

    worktree_ttl = args.worktree_ttl if args.worktree_ttl is not None else DEFAULT_WORKTREE_TTL_HOURS
    lock_ttl = args.lock_ttl if args.lock_ttl is not None else DEFAULT_LOCK_TTL_HOURS

    report = purge(
        project_dir,
        apply=bool(args.apply),
        worktree_ttl_hours=worktree_ttl,
        lock_ttl_hours=lock_ttl,
    )

    if getattr(args, "json_output", False):
        import json as _json
        print(_json.dumps({
            "dry_run": report.dry_run,
            "candidates": [
                {"path": str(c.path), "kind": c.kind, "reason": c.reason,
                 "age_hours": (None if c.age_hours == float("inf") else round(c.age_hours, 2)),
                 "branch": c.branch}
                for c in report.candidates
            ],
            "protected": [
                {"path": str(p.path), "kind": p.kind, "reason": p.reason}
                for p in report.protected
            ],
            "purged": report.purged,
            "errors": report.errors,
        }, indent=2))
    else:
        print(format_report(report))

    # Exit 1 on a dry run that found debris, so CI can gate on a dirty tree.
    if report.errors:
        return 1
    if report.dry_run and report.candidates:
        return 1
    return 0


def cmd_telemetry(args: argparse.Namespace) -> int:
    """Manage anonymous, opt-in product telemetry (default OFF, local-first).

    See product_intelligence.py for the full privacy contract: an allow-list
    sanitizer enforced in code (not trust) means code/paths/secrets/prompts
    can never be recorded even if a future call site tried to send them.
    """
    from genesis_architect_pro.product_intelligence import (
        CONSENT_PROMPT, clear_events, describe_payload, needs_consent_prompt,
        revoke_consent, set_consent,
    )

    project_dir = Path(args.dir).expanduser().resolve()
    action = getattr(args, "telemetry_action", None)

    if action == "enable":
        set_consent(True, project_dir)
        print("\n  Telemetry enabled — anonymous, local-first. "
              "Run `genesis telemetry status` any time to see what's stored.\n")
        return 0
    if action == "disable":
        revoke_consent(project_dir)
        print("\n  Telemetry disabled. This stops new collection; existing local "
              "events are kept — run `genesis telemetry clear` to delete them too.\n")
        return 0
    if action == "clear":
        n = clear_events(project_dir)
        print(f"\n  Cleared {n} locally-stored event(s).\n")
        return 0

    # "status" or bare `genesis telemetry`.
    print()
    if needs_consent_prompt(project_dir):
        print(CONSENT_PROMPT)
        print()
        print("  Decide with: genesis telemetry enable   |   genesis telemetry disable")
    else:
        print(describe_payload(project_dir))
    print()
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="genesis",
        description="Genesis Decision Engine — route any instruction to the right engines",
        epilog=(
            "Core commands (from genesis-architect):\n"
            "  init       Scan GitHub repos, mine pitfalls, and scaffold your project\n"
            "  research   Multi-source research on a topic (--json-data to process results)\n"
            "  publish    Generate Show HN post and GitHub Release notes\n"
            "  config     Manage API keys (set / get / show)\n"
            "  upgrade    Show Pro status and how to unlock advanced features\n"
            "\nNot sure which command runs the engine you want?\n"
            "  genesis engines        Every engine, and the command that reaches it\n"
            "\nRun `genesis <command> --help` for details on any command."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    decide.add_argument("--json", dest="json_output", action="store_true",
                        help="Output structured JSON (implies --no-commit)")

    explain = sub.add_parser("explain", help="Print the last session's decision log")
    explain.add_argument("--dir", default=".", metavar="PATH",
                         help="Project directory (default: current directory)")
    explain.add_argument("--json", dest="json_output", action="store_true",
                         help="Output structured JSON (for piping / CI)")

    memory = sub.add_parser("memory", help="Show or manage per-project memory (.genesis/*.md)")
    memory.add_argument("--dir", default=".", metavar="PATH",
                        help="Project directory (default: current directory)")
    memory.add_argument("--init", action="store_true",
                        help="Initialise memory files under .genesis/")
    memory.add_argument("--status", action="store_true",
                        help="Show memory file status (exists, size)")
    memory.add_argument("--sessions", action="store_true",
                        help="Show restorable cross-session context instead of the .genesis/ files")
    memory.add_argument("--json", dest="json_output", action="store_true",
                        help="Output structured JSON (for piping / CI)")

    engines_p = sub.add_parser(
        "engines", help="List every engine and the command that reaches it")
    engines_p.add_argument("--modules", action="store_true",
                           help="Show the implementing module next to each engine")
    engines_p.add_argument("--json", dest="json_output", action="store_true",
                           help="Output structured JSON (for piping / CI)")

    deps_p = sub.add_parser(
        "deps", help="Third-party dependencies per module, plus their advisories")
    deps_p.add_argument("path", nargs="?", default=".", metavar="PATH",
                        help="Project directory to scan (default: current directory)")
    deps_p.add_argument("--package", default=None, metavar="NAME",
                        help="Skip the project scan and report on one package instead")
    deps_p.add_argument("--ecosystem", default=None, metavar="NAME",
                        help="Registry for --package: pypi | npm | crates | maven | nuget "
                             "(default: pypi)")
    deps_p.add_argument("--no-cve", action="store_true",
                        help="Skip the advisory lookup (no network calls)")
    deps_p.add_argument("--json", dest="json_output", action="store_true",
                        help="Output structured JSON (for piping / CI)")

    ui = sub.add_parser("ui", help="Generate the self-contained HTML Canvas workspace")
    ui.add_argument("--dir", default=".", metavar="PATH",
                    help="Project directory (default: current directory)")
    ui.add_argument("--output", default=None, metavar="PATH",
                    help="Output filename, written under .genesis/ui/ (default: workspace.html)")
    ui.add_argument("--open", action="store_true",
                    help="Open the workspace in the default browser after generating")

    companion = sub.add_parser("companion", help="Start the Genesis PRO health page server")
    companion.add_argument("--dir", default=".", metavar="PATH",
                           help="Project directory (default: current directory)")
    companion.add_argument("--port", type=int, default=7433, metavar="PORT",
                           help="Port for the health page (default: 7433, auto-scans if taken)")
    companion.add_argument("--stats", action="store_true",
                           help="Print gate miss-rate stats and exit (no server)")
    companion.add_argument("--no-browser", action="store_true",
                           help="Do not open the browser automatically")
    companion.add_argument("--setup", action="store_true",
                           help="Download local voice models (STT/TTS) into ~/.genesis/models")
    companion.add_argument("--check", action="store_true",
                           help="Report voice readiness (STT/TTS) without downloading")
    companion.add_argument("--speak", default=None, metavar="TEXT",
                           help="Speak a phrase to verify the voice round-trip (he/en auto-detected)")
    companion.add_argument("--serve", action="store_true",
                           help="Start full Companion backend (WebSocket 47291 + IDE bridge 47292) for Tauri")
    companion.add_argument("--ui", action="store_true",
                           help="Launch the Floating Assistant: start the backend and open the web UI wired to it")
    companion.add_argument("--listen", action="store_true",
                           help="Listen for the wake word ('genesis' or the Hebrew equivalent) and print recognized instructions")

    sync = sub.add_parser("sync", help="Run the autonomous sync manager (gate + findings + auto-apply)")
    sync.add_argument("--dir", default=".", metavar="PATH",
                      help="Project directory (default: current directory)")
    sync.add_argument("--dry-run", action="store_true",
                      help="Analyse only — write nothing to disk")
    sync.add_argument("--report-only", action="store_true",
                      help="Skip auto-apply writes but still print the report")
    sync.add_argument("--auto-apply", action="store_true", default=True,
                      help="Auto-apply GREEN zone writes (default: on)")
    sync.add_argument("--no-auto-apply", dest="auto_apply", action="store_false",
                      help="Disable GREEN zone auto-apply")
    sync.add_argument("--json", dest="json_output", action="store_true",
                      help="Output structured JSON (for piping / CI)")
    sync.add_argument("--ci-mode", action="store_true",
                      help="Exit 1 if any yellow/red findings (for CI pipelines)")

    doctor_p = sub.add_parser("doctor", help="Readiness check: Pro install, optional deps")
    doctor_p.add_argument("--json", dest="json_output", action="store_true",
                          help="Output structured JSON (for piping / CI)")

    recover = sub.add_parser(
        "recover", help="Diagnose project health: drift, broken imports, anti-patterns, decay")
    recover.add_argument("path", nargs="?", default=".", metavar="PATH",
                         help="Project directory to scan (default: current directory)")
    recover.add_argument("--resume", action="store_true",
                         help="Resume a saved session instead of starting fresh")
    recover.add_argument("--serial", action="store_true",
                         help="Run engines serially (useful for debugging)")
    recover.add_argument("--classify-only", action="store_true",
                         help="Only classify the instruction — do not run engines")
    recover.add_argument("--yes", "-y", action="store_true",
                         help="Auto-approve all write operations (CI mode)")
    recover.add_argument("--no-commit", action="store_true",
                         help="Skip APPROVE/COMMIT — analysis only")
    recover.add_argument("--json", dest="json_output", action="store_true",
                         help="Output structured JSON (implies --no-commit)")

    harden = sub.add_parser(
        "harden", help="Security gate: STRIDE threat model + OWASP Top 10 + secrets scan")
    harden.add_argument("path", nargs="?", default=".", metavar="PATH",
                        help="Project directory to harden (default: current directory)")
    harden.add_argument("--resume", action="store_true",
                        help="Resume a saved session instead of starting fresh")
    harden.add_argument("--serial", action="store_true",
                        help="Run engines serially (useful for debugging)")
    harden.add_argument("--classify-only", action="store_true",
                        help="Only classify the instruction — do not run engines")
    harden.add_argument("--yes", "-y", action="store_true",
                        help="Auto-approve all write operations (CI mode)")
    harden.add_argument("--no-commit", action="store_true",
                        help="Skip APPROVE/COMMIT — analysis only")
    harden.add_argument("--json", dest="json_output", action="store_true",
                        help="Output structured JSON (implies --no-commit)")

    advise_p = sub.add_parser(
        "advise", help="Recommend MCP servers and skills for this project (installs nothing)")
    advise_p.add_argument("--dir", default=".", metavar="PATH",
                          help="Project directory (default: current directory)")
    advise_p.add_argument("--local-only", action="store_true",
                          help="Only project-level recommendations")
    advise_p.add_argument("--global-only", action="store_true",
                          help="Only cross-project recommendations from learning history")
    advise_p.add_argument("--json", dest="json_output", action="store_true",
                          help="Output structured JSON (for piping / CI)")

    fetch_p = sub.add_parser(
        "fetch", help="Fetch a trusted skill pack into the sandbox (read-only, never executed)")
    fetch_p.add_argument("source_id", nargs="?", default=None, metavar="SOURCE",
                         help="Trusted source id (omit to list what's fetchable)")
    fetch_p.add_argument("--dir", default=".", metavar="PATH",
                         help="Project directory (default: current directory)")
    fetch_p.add_argument("--list", dest="list_sources", action="store_true",
                         help="List the trusted registry and exit")
    fetch_p.add_argument("--ttl", type=float, default=None, metavar="HOURS",
                         help="Sandbox TTL in hours (default and maximum: 2)")
    fetch_p.add_argument("--force", action="store_true",
                         help="Re-clone even if the sandbox already exists")
    fetch_p.add_argument("--discard", action="store_true",
                         help="Remove this source's sandbox now instead of fetching")
    fetch_p.add_argument("--json", dest="json_output", action="store_true",
                         help="Output structured JSON (for piping / CI)")

    purge_p = sub.add_parser(
        "purge", help="Auto-Purge: find (and optionally remove) expired ephemeral resources")
    purge_p.add_argument("--dir", default=".", metavar="PATH",
                         help="Project directory (default: current directory)")
    purge_p.add_argument("--apply", action="store_true",
                         help="Actually remove what was found (default: dry run only)")
    purge_p.add_argument("--worktree-ttl", type=float, default=None, metavar="HOURS",
                         help="Idle hours before a clean worktree is expired (default: 168)")
    purge_p.add_argument("--lock-ttl", type=float, default=None, metavar="HOURS",
                         help="Age in hours before a dead-owner lock is expired (default: 1)")
    purge_p.add_argument("--json", dest="json_output", action="store_true",
                         help="Output structured JSON (for piping / CI)")

    telemetry_p = sub.add_parser(
        "telemetry", help="Manage anonymous, opt-in product telemetry (default OFF)")
    telemetry_p.add_argument("--dir", default=".", metavar="PATH",
                             help="Project directory (default: current directory)")
    telemetry_sub = telemetry_p.add_subparsers(dest="telemetry_action")
    for _name, _help in (
        ("status", "Show consent state and what's stored locally"),
        ("enable", "Turn telemetry on (generates an anonymous install id)"),
        ("disable", "Turn telemetry off (keeps existing local events)"),
        ("clear", "Delete all locally-stored telemetry events"),
    ):
        _sub_p = telemetry_sub.add_parser(_name, help=_help)
        _sub_p.add_argument("--dir", default=".", metavar="PATH",
                            help="Project directory (default: current directory)")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    # Legacy Windows consoles default to cp1252 — emoji/box characters in our
    # output would raise UnicodeEncodeError. Degrade to replacement chars.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (OSError, ValueError):
                pass

    parser = _build_parser()

    if argv is None:
        argv = sys.argv[1:]

    # Pro owns these subcommands; the core Typer CLI owns the rest. The two
    # packages both ship a `genesis` console-script, and whichever installs
    # last wins the launcher — so Pro's entry point must delegate core
    # commands to the core app instead of forcing everything into `decide`.
    _pro_cmds = ("decide", "explain", "memory", "ui", "companion", "sync",
                 "doctor", "recover", "harden", "telemetry", "purge", "advise", "fetch",
                 "engines", "deps")
    _core_cmds = ("init", "config", "research", "publish", "upgrade", "resolve")
    if argv and argv[0] in _core_cmds:
        from genesis_architect.cli import app as _core_app
        return _core_app(args=argv, prog_name="genesis", standalone_mode=False) or 0

    _known = _pro_cmds + ("-h", "--help")
    if argv and argv[0] not in _known:
        first = argv[0]
        # A single word with no whitespace looks like a mistyped/unregistered
        # command name rather than a free-text instruction. If it matches
        # *zero* intent signals (the classifier's raw_score == 0 case), routing
        # it into `decide` would silently produce a low-confidence COMMITTEE
        # guess with no indication the command itself doesn't exist. Anything
        # that matches at least one signal (e.g. a terse "refactor") still
        # falls through to decide as before — only truly unknown tokens stop.
        if (first and not first.startswith("-") and not first.isspace()
                and " " not in first and "\t" not in first):
            from genesis_architect_pro.intent_classifier import classify
            if not classify(first).signals:
                print(
                    f"\nUnknown command '{first}'.\n"
                    f"Did you mean to describe what you want in a full sentence?\n"
                    f"  genesis decide \"{first} ...\"\n"
                    f"  genesis --help\n",
                    file=sys.stderr,
                )
                return 1
        # A bare instruction with no subcommand → treat as a GDE session.
        argv = ["decide"] + argv

    args = parser.parse_args(argv)

    _dispatch = {
        "decide": cmd_decide,
        "explain": cmd_explain,
        "memory": cmd_memory,
        "ui": cmd_ui,
        "companion": cmd_companion,
        "sync": cmd_sync,
        "doctor": cmd_doctor,
        "recover": cmd_recover,
        "harden": cmd_harden,
        "telemetry": cmd_telemetry,
        "purge": cmd_purge,
        "advise": cmd_advise,
        "fetch": cmd_fetch,
        "engines": cmd_engines,
        "deps": cmd_deps,
    }
    handler = _dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 0

    rc = handler(args)
    _emit_hygiene_notice(args)
    return rc


def _emit_hygiene_notice(args: argparse.Namespace) -> None:
    """Surface expired ephemeral resources at the end of a run.

    Read-only: it runs Auto-Purge in dry-run mode and only prints. It exists
    so debris announces itself instead of waiting to be remembered — but it
    must never delete anything on its own, and never break the command that
    just succeeded, so every failure here is swallowed.

    Skipped for `purge` itself (which just reported in full) and `doctor`
    (a readiness surface that shouldn't grow unrelated noise).
    """
    if getattr(args, "command", None) in ("purge", "doctor"):
        return
    try:
        from genesis_architect_pro.ephemeral_purge import hygiene_notice

        project_dir = Path(getattr(args, "dir", None) or getattr(args, "path", ".") or ".")
        notice = hygiene_notice(project_dir.expanduser().resolve())
        if notice:
            print(f"\n  {notice}\n")
    except Exception:  # noqa: BLE001 — a hygiene hint must never break a command
        pass


if __name__ == "__main__":
    sys.exit(main())
