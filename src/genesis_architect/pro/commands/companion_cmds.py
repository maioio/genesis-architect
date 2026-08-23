"""The `genesis companion` command family — Floating Assistant, backend, voice.

Split out of gde_cli.py verbatim. This is the widest handler cluster in the
CLI: the streaming server, the IDE bridge, the wake-word listener, the
notifier and the generated web UI all hang off these four commands.

Every one of those imports is deferred into the handler that needs it, which
is what keeps the optional subsystems optional — `genesis companion --stats`
must work on an install with no websockets, no voice models and no Rich.
"""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from genesis_architect.pro.commands.companion_backend import (
    start_backend,
    stop_backend,
)
from genesis_architect.pro.commands.formatting import _use_rich
from genesis_architect.pro.commands.voice_setup import (
    _auto_setup_voice,
    _companion_check,
    _companion_setup,
    _companion_speak,
)


def cmd_companion_serve(project_dir: Path) -> int:
    """Start the full Companion backend (WebSocket + IDE bridge) for Tauri.

    Prints READY token=<64-hex-chars> to stdout, then blocks until killed.
    Handles SIGTERM and SIGINT for graceful shutdown.
    """
    import signal
    import socket

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

    # 1-5. Server, runner patch, IDE bridge, gate notifier, inbound router —
    #      the same sequence `--ui` runs. See commands/companion_backend.py.
    backend = start_backend(project_dir)

    # 6. Print READY line so Tauri can extract the token
    token = backend.token
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
    stop_backend(backend)

    return 0


def cmd_companion_listen(project_dir: Path) -> int:
    """Listen for the wake word and print recognized instructions. Honest about
    readiness: if the mic or STT model is missing, it says exactly what to do."""
    import time

    from genesis_architect.pro.voice.listener import WakeWordListener, mic_status

    mic = mic_status()
    print("\n  Genesis voice listener")
    print(f"  Microphone: {'ready — ' + mic.detail if mic.available else 'NOT ready — ' + mic.detail}")
    if not mic.available:
        print("  Install the voice extra: pip install genesis-architect[voice]\n")
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

    from genesis_architect.pro.companion_ui import write_companion_html, DEFAULT_PORT

    # Auto-download voice models on first launch if packages are installed but models missing.
    _auto_setup_voice()

    token = ""
    ws_server = None
    try:
        # The same sequence `--serve` runs. See commands/companion_backend.py.
        #
        # One narrow difference from the inline version this replaced: that
        # code assigned ws_server before the later steps, so a failure *after*
        # the socket opened left a live server with no router wired, and this
        # command then blocked forever serving a backend that could not answer
        # anything. start_backend() is atomic, so a partial failure now leaves
        # ws_server as None and the offline UI path is taken instead. Only the
        # error path differs, and only in that direction.
        backend = start_backend(project_dir)
        ws_server = backend.server
        router = backend.router
        token = backend.token
        port = backend.port
        print(f"\n  Genesis Companion backend running (ws 127.0.0.1:{port}).")
    except Exception as exc:  # noqa: BLE001
        port = DEFAULT_PORT
        router = None
        print(f"\n  Backend not started ({exc}).")
        print("  Opening the UI in offline mode. For live engines, install:")
        print("    pip install genesis-architect[streaming]\n")

    # Wake word -> the same router the panel's WebSocket uses, so "genesis ..."
    # spoken aloud behaves exactly like typing the instruction into the panel:
    # same GDE pipeline, same engine/gate events streamed back to the open UI.
    # Previously --listen (wake word) and --ui (the panel) were two disconnected
    # commands - you could have one or the other, never both together.
    wake_listener = None
    if ws_server is not None and router is not None:
        try:
            from genesis_architect.pro.streaming.events import MessageType, StreamMessage
            from genesis_architect.pro.voice.listener import WakeWordListener

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
        from genesis_architect.pro.companion_ui import render_companion_html
        from genesis_architect.pro.companion_window import run_floating_window

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
    from genesis_architect.pro.gde_companion import (
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
