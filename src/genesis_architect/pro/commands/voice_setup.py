"""Voice provisioning and the `genesis companion` sub-actions it backs.

Split out of gde_cli.py verbatim. `--setup`, `--check` and `--speak` are thin
wrappers over the voice subsystem, and the first-launch provisioning they
share is the largest single piece of logic behind `companion --ui`.

The provisioning gate lives here too. `_auto_setup_voice()` shells out to pip
and downloads ~1-2 GB of models, so it runs only when a human is watching:
see `_auto_install_disabled()` for the three independent reasons it stands
down.
"""

from __future__ import annotations

import sys

from genesis_architect.pro.commands.formatting import _hr, _use_rich


def _companion_check() -> int:
    """Report voice readiness (STT/TTS) without downloading anything."""
    from genesis_architect.pro.voice import readiness

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
    from genesis_architect.pro.voice import run_setup, readiness

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
    from genesis_architect.pro.voice import TTSPipeline, Urgency, detect_lang, readiness

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

#: Set to any non-empty value to stop `genesis companion --ui` from installing
#: packages or downloading models into the current environment. Intended for
#: CI, reproducible/pinned installs, offline machines, and test runs - which
#: must never mutate the environment they are running in.
NO_AUTO_INSTALL_ENV = "GENESIS_NO_AUTO_INSTALL"


def _stdio_is_interactive() -> bool:
    """True only when both stdin and stdout are real terminals.

    Provisioning downloads ~1-2 GB and can sit in pip for up to 30 minutes.
    That is reasonable in front of a human who just typed the command and can
    watch it or Ctrl-C it. Behind a pipe, a service manager, a container, or
    an IDE task runner there is nobody to do either, so the launcher simply
    appears to hang.

    Streams get replaced by objects that have no ``isatty`` (pytest capture)
    or are already closed, and on Windows ``pythonw`` leaves them as ``None``.
    Anything we cannot ask is treated as "not a terminal" — the safe answer,
    since guessing wrong costs a 30-minute stall.
    """
    for stream in (sys.stdin, sys.stdout):
        try:
            if not stream.isatty():
                return False
        except (AttributeError, ValueError):
            return False
    return True


def _auto_install_disabled() -> bool:
    """True when auto-provisioning must not run.

    Three independent reasons, in order of explicitness: the operator opted
    out, we are under pytest, or there is no terminal attached. The pytest
    check is a safety net, not the contract — a test that reaches this path
    should still mock it. Without the net, a single unmocked call
    pip-installs into the developer's environment mid-suite.
    """
    import os
    if os.environ.get(NO_AUTO_INSTALL_ENV, "").strip():
        return True
    if "PYTEST_CURRENT_TEST" in os.environ:
        return True
    return not _stdio_is_interactive()


def _auto_setup_voice() -> None:
    """Make voice fully ready on first launch: install any missing Companion
    packages into this environment, then download the STT/TTS models.

    This is the one-command experience — a user installs `genesis-architect`
    and the first `genesis companion --ui` provisions everything else
    automatically. Shows progress; never raises.

    No-op unless a human is watching: see `_auto_install_disabled()`. Opt out
    explicitly with ``GENESIS_NO_AUTO_INSTALL=1``.
    """
    if _auto_install_disabled():
        return

    # setup.py is import-safe with nothing extra installed — import it directly
    # (the voice package __init__ pulls modules that need the extras).
    from genesis_architect.pro.voice.setup import (
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
