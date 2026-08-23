"""Project-state commands — memory, workspace, hygiene, readiness, licence.

Split out of gde_cli.py verbatim. These read or tidy what Genesis has stored
about a project, rather than analysing the project itself.

`purge` is dry-run by default and deletes only under `--apply`; `doctor`
reports readiness without changing anything. Both are deliberately safe to
run blind.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from genesis_architect.pro.commands.formatting import (
    _hr,
    _jsonable,
    _use_rich,
)


def cmd_memory(args: argparse.Namespace) -> int:
    """Show or update the per-project memory under .genesis/."""
    from genesis_architect.pro.memory_engine import (
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
    from genesis_architect.pro.cross_session_memory import (
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
    from genesis_architect.pro.capability_map import format_map, to_dict

    if getattr(args, "json_output", False):
        import json as _json
        print(_json.dumps(to_dict(), indent=2))
        return 0

    print(format_map(show_modules=getattr(args, "modules", False)))
    return 0
def cmd_ui(args: argparse.Namespace) -> int:
    """Generate (or open) the self-contained HTML workspace."""
    from genesis_architect.pro.ui_workspace import write_workspace

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
def cmd_doctor(args: argparse.Namespace) -> int:
    """Readiness report: install health and optional dependencies.

    This is the tool you run to find out *why* nothing else works, so it must
    stay answerable even when the rest of the CLI cannot run.
    """
    from genesis_architect.pro.first_run import check_readiness, doctor_report

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
def cmd_license(args: argparse.Namespace) -> int:
    """Report licensing status.

    Genesis Architect has no paid tier: every engine is free and open source
    under AGPL-3.0. This command is kept so that muscle memory and old scripts
    (`genesis license activate ...`) get a clear answer instead of an error.
    """
    print()
    print("  Genesis Architect is free and open source (AGPL-3.0).")
    print("  There is no license key, no paid tier, and nothing gated —")
    print("  every engine is available in this install.")
    print()
    print("  Source:  https://github.com/maioio/genesis-architect")
    print()
    return 0
def cmd_purge(args: argparse.Namespace) -> int:
    """`genesis purge [--apply]` — Auto-Purge for expired ephemeral resources.

    Dry run by default: it reports what expired and what it refused to touch,
    and deletes nothing. `--apply` is the only path that removes anything.
    """
    from genesis_architect.pro.ephemeral_purge import (
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
