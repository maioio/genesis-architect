"""genesis — engine CLI entry point (compatibility surface).

Usage::

    genesis decide "diagnose the project and identify drift"
    genesis recover [PATH]
    genesis companion --ui

The implementation lives in `genesis_architect.pro.commands`:

    commands/parser.py             every subcommand, flag and help string
    commands/router.py             argv routing and dispatch — `main()` is here
    commands/formatting.py         Rich output, plain-text fallbacks, prompts
    commands/session_cmds.py       decide, recover, harden, explain
    commands/companion_cmds.py     the companion family
    commands/companion_backend.py  the startup --serve and --ui share
    commands/voice_setup.py        voice provisioning + companion --setup/check/speak
    commands/project_cmds.py       memory, ui, purge, doctor, engines, license
    commands/analysis_cmds.py      deps, advise, fetch, sync, telemetry

Named `commands` rather than `cli` on purpose: `genesis_architect.cli` is
already the Typer app for the scaffolding commands, and two sibling modules
named `cli` in one distribution is a readability hazard even though the
namespaces do not collide.

This module stays because `genesis_architect.cli_entry` imports `main` from
here, and that is what `pyproject.toml` declares as the console script. Entry
points resolve at install time, so repointing the chain would require a
reinstall in every existing environment for no user-visible gain. It also
keeps the names the test suite reaches for importable from where they have
always been.

Names resolve lazily (PEP 562), the same way the package facade does, so
importing this module costs one small file rather than the whole CLI —
`--help` no longer drags in the streaming, voice and engine layers.
"""

from __future__ import annotations

_LAZY_EXPORTS: dict[str, str] = {
    # analysis_cmds
    "cmd_advise": "genesis_architect.pro.commands.analysis_cmds",
    "cmd_deps": "genesis_architect.pro.commands.analysis_cmds",
    "cmd_fetch": "genesis_architect.pro.commands.analysis_cmds",
    "cmd_sync": "genesis_architect.pro.commands.analysis_cmds",
    "cmd_telemetry": "genesis_architect.pro.commands.analysis_cmds",
    # companion_backend
    "start_backend": "genesis_architect.pro.commands.companion_backend",
    "stop_backend": "genesis_architect.pro.commands.companion_backend",
    # companion_cmds
    "cmd_companion": "genesis_architect.pro.commands.companion_cmds",
    "cmd_companion_listen": "genesis_architect.pro.commands.companion_cmds",
    "cmd_companion_serve": "genesis_architect.pro.commands.companion_cmds",
    "cmd_companion_ui": "genesis_architect.pro.commands.companion_cmds",
    # formatting
    "_failure_modes_for": "genesis_architect.pro.commands.formatting",
    "_hr": "genesis_architect.pro.commands.formatting",
    "_jsonable": "genesis_architect.pro.commands.formatting",
    "_print_report_summary": "genesis_architect.pro.commands.formatting",
    "_prompt_approval": "genesis_architect.pro.commands.formatting",
    "_rich_approval": "genesis_architect.pro.commands.formatting",
    "_rich_classify": "genesis_architect.pro.commands.formatting",
    "_rich_commit": "genesis_architect.pro.commands.formatting",
    "_rich_header": "genesis_architect.pro.commands.formatting",
    "_rich_report": "genesis_architect.pro.commands.formatting",
    "_use_rich": "genesis_architect.pro.commands.formatting",
    # parser
    "_build_parser": "genesis_architect.pro.commands.parser",
    # project_cmds
    "_cmd_memory_sessions": "genesis_architect.pro.commands.project_cmds",
    "cmd_doctor": "genesis_architect.pro.commands.project_cmds",
    "cmd_engines": "genesis_architect.pro.commands.project_cmds",
    "cmd_license": "genesis_architect.pro.commands.project_cmds",
    "cmd_memory": "genesis_architect.pro.commands.project_cmds",
    "cmd_purge": "genesis_architect.pro.commands.project_cmds",
    "cmd_ui": "genesis_architect.pro.commands.project_cmds",
    # router
    "_emit_hygiene_notice": "genesis_architect.pro.commands.router",
    "main": "genesis_architect.pro.commands.router",
    # session_cmds
    "cmd_decide": "genesis_architect.pro.commands.session_cmds",
    "cmd_explain": "genesis_architect.pro.commands.session_cmds",
    "cmd_harden": "genesis_architect.pro.commands.session_cmds",
    "cmd_recover": "genesis_architect.pro.commands.session_cmds",
    # voice_setup
    "NO_AUTO_INSTALL_ENV": "genesis_architect.pro.commands.voice_setup",
    "_auto_install_disabled": "genesis_architect.pro.commands.voice_setup",
    "_auto_setup_voice": "genesis_architect.pro.commands.voice_setup",
    "_companion_check": "genesis_architect.pro.commands.voice_setup",
    "_companion_setup": "genesis_architect.pro.commands.voice_setup",
    "_companion_speak": "genesis_architect.pro.commands.voice_setup",
    "_stdio_is_interactive": "genesis_architect.pro.commands.voice_setup",
}


def main(argv: list[str] | None = None) -> int:
    """The `genesis` console script.

    Defined rather than lazily re-exported: this is the declared entry point,
    and a real function keeps the import deferred to call time without relying
    on module `__getattr__` being consulted for it.
    """
    from genesis_architect.pro.commands.router import main as _main

    return _main(argv)


def __getattr__(name: str):
    """Resolve a CLI name on first access (PEP 562).

    The resolved object is cached in module globals, so this runs once per
    name and later access is an ordinary attribute lookup.
    """
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    import importlib

    value = getattr(importlib.import_module(module_path), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


if __name__ == "__main__":
    import sys

    sys.exit(main())
