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
            for fname, info in status.items():
                exists = "[green]yes[/green]" if info.get("exists") else "[dim]no[/dim]"
                size = f"{info.get('size', 0)} bytes" if info.get("exists") else "—"
                table.add_row(fname, exists, size)
            console.print(table)
            console.print()
        else:
            print()
            print("  Project Memory Status")
            print(_hr())
            for fname, info in status.items():
                exists = "yes" if info.get("exists") else "no"
                size = f"{info.get('size', 0)} bytes" if info.get("exists") else "—"
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


def cmd_ui(args: argparse.Namespace) -> int:
    """Generate (or open) the self-contained HTML workspace."""
    from genesis_architect_pro.ui_workspace import collect_state, write_workspace

    project_dir = Path(args.dir).expanduser().resolve()
    if not project_dir.is_dir():
        print(f"  error: --dir '{project_dir}' is not a directory", file=sys.stderr)
        return 1

    output_path = Path(args.output) if args.output else project_dir / ".genesis" / "workspace.html"

    state = collect_state(project_dir)
    written = write_workspace(state, output_path)

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

    from genesis_architect_pro.gde_companion import GateNotifier
    from genesis_architect_pro.streaming.server import CompanionServer
    from genesis_architect_pro.ide_bridge.server import IDEBridgeServer
    from genesis_architect_pro.streaming import runner_patch
    from genesis_architect_pro import gate_notifier_patch
    from genesis_architect_pro.streaming.inbound import InboundRouter
    from genesis_architect_pro.streaming.events import default_emitter

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
        print(f"\n  Backend not started ({exc}).")
        print("  Opening the UI in offline mode. For live engines, install:")
        print("    pip install genesis-architect-pro[streaming]\n")

    ui_path = write_companion_html(project_dir, ws_port=port, ws_token=token)
    if ui_path is None:
        print("  error: could not write the UI file.", file=sys.stderr)
        return 1
    print(f"  Floating Assistant: {ui_path}")
    if not no_browser:
        webbrowser.open(ui_path.as_uri())
        print("  Opened in your browser. Close this terminal (Ctrl+C) to stop.\n")

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
    try:
        ws_server.stop()
    except Exception:
        pass
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

    memory = sub.add_parser("memory", help="Show or manage per-project memory (.genesis/*.md)")
    memory.add_argument("--dir", default=".", metavar="PATH",
                        help="Project directory (default: current directory)")
    memory.add_argument("--init", action="store_true",
                        help="Initialise memory files under .genesis/")
    memory.add_argument("--status", action="store_true",
                        help="Show memory file status (exists, size)")

    ui = sub.add_parser("ui", help="Generate the self-contained HTML Canvas workspace")
    ui.add_argument("--dir", default=".", metavar="PATH",
                    help="Project directory (default: current directory)")
    ui.add_argument("--output", default=None, metavar="PATH",
                    help="Output path (default: .genesis/workspace.html)")
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
    _known = ("decide", "explain", "memory", "ui", "companion", "sync", "-h", "--help")
    if argv and argv[0] not in _known:
        argv = ["decide"] + argv

    args = parser.parse_args(argv)

    # Every command in this CLI is a Pro feature — enforce the license once
    # here at the entry point (offline Ed25519 check, no phone-home).
    from genesis_architect_pro.license import LicenseError, require_license
    try:
        require_license(f"genesis {args.command or ''}".strip())
    except LicenseError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2

    if args.command == "decide":
        return cmd_decide(args)
    if args.command == "explain":
        return cmd_explain(args)
    if args.command == "memory":
        return cmd_memory(args)
    if args.command == "ui":
        return cmd_ui(args)
    if args.command == "companion":
        return cmd_companion(args)
    if args.command == "sync":
        return cmd_sync(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
