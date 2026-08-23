"""CLI entry point — argv routing and command dispatch.

Split out of gde_cli.py verbatim.

Two lists have to agree for a subcommand to be reachable, and they live here
together for that reason. `_pro_cmds` decides whether argv[0] is a subcommand
at all — anything absent from it falls through to `decide` as free text — and
`_dispatch` maps the name to its handler. A parser entry with no `_pro_cmds`
entry is a command that exists and cannot be reached, which is worse than one
that does not exist; keeping both in one file is what makes that mismatch
visible in review.

The scaffolding commands are delegated to the Typer app in
`genesis_architect.cli` rather than reimplemented: both command families share
one `genesis` binary, and this dispatcher owns the split.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from genesis_architect.pro.commands.analysis_cmds import (
    cmd_advise,
    cmd_deps,
    cmd_fetch,
    cmd_sync,
    cmd_telemetry,
)
from genesis_architect.pro.commands.companion_cmds import (
    cmd_companion,
)
from genesis_architect.pro.commands.project_cmds import (
    cmd_doctor,
    cmd_engines,
    cmd_license,
    cmd_memory,
    cmd_purge,
    cmd_ui,
)
from genesis_architect.pro.commands.session_cmds import (
    cmd_decide,
    cmd_explain,
    cmd_harden,
    cmd_recover,
)
from genesis_architect.pro.commands.parser import _build_parser


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

    # One binary, two command families: the engine commands below are argparse
    # (this module), the scaffolding ones are Typer (genesis_architect.cli).
    # This dispatcher owns the former and delegates the latter, so an unknown
    # first token is never silently forced into `decide`.
    _pro_cmds = ("decide", "explain", "memory", "ui", "companion", "sync",
                 "doctor", "recover", "harden", "telemetry", "purge", "advise", "fetch",
                 "engines", "deps", "license")
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
            from genesis_architect.pro.intent_classifier import classify
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
        "license": cmd_license,
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
        from genesis_architect.pro.ephemeral_purge import hygiene_notice

        project_dir = Path(getattr(args, "dir", None) or getattr(args, "path", ".") or ".")
        notice = hygiene_notice(project_dir.expanduser().resolve())
        if notice:
            print(f"\n  {notice}\n")
    except Exception:  # noqa: BLE001 — a hygiene hint must never break a command
        pass
