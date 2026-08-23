"""Command-line surface definition — every subcommand, flag and help string.

Split out of gde_cli.py verbatim. It is the largest single thing in that
module and the least entangled: it touches nothing but argparse, so it moved
without a line changing.

Keeping the whole surface in one file is deliberate. `--help` output and
command discovery are the parts of a CLI users actually depend on, and they
stay consistent by being defined in one place rather than assembled from
fragments spread across the handler modules.
"""

from __future__ import annotations

import argparse


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

    doctor_p = sub.add_parser("doctor", help="Readiness check: install health and optional deps")
    doctor_p.add_argument("--json", dest="json_output", action="store_true",
                          help="Output structured JSON (for piping / CI)")

    # Kept only so old scripts and muscle memory get a clear answer: Genesis
    # is free and open source, there is no key to activate.
    license_p = sub.add_parser("license", help="(No license needed — Genesis is free)")
    license_sub = license_p.add_subparsers(dest="license_action")
    activate_p = license_sub.add_parser("activate", help="(No longer needed)")
    activate_p.add_argument("key", nargs="?", help="(ignored)")
    license_sub.add_parser("status", help="Show licensing status")

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
