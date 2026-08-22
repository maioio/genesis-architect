"""genesis — CLI entry point (compatibility surface).

Usage::

    genesis decide "diagnose the project and identify drift"
    genesis decide "refactor the import module to reduce coupling" --dir /path
    genesis gate --json
    genesis companion --ui

The implementation lives in `genesis_architect_pro.cli`:

    cli/parser.py           every subcommand, flag and help string
    cli/router.py           argv routing and dispatch — `main()` is here
    cli/formatting.py       Rich output, plain-text fallbacks, prompts
    cli/session_cmds.py     decide, recover, harden, explain
    cli/companion_cmds.py   the companion family
    cli/voice_setup.py      voice provisioning + companion --setup/check/speak
    cli/project_cmds.py     memory, ui, purge, doctor, engines
    cli/analysis_cmds.py    gate, deps, advise, fetch, sync, telemetry

This module stays because `pyproject.toml` declares
``genesis = "genesis_architect_pro.gde_cli:main"``. Entry points resolve at
install time, so repointing it would require a reinstall in every existing
environment for no user-visible gain. It also keeps the names the test suite
reaches for importable from where they have always been.

Names resolve lazily (PEP 562), the same way the package facade does, so
importing this module costs one small file rather than the whole CLI. That
also means `import genesis_architect_pro.gde_cli` no longer drags in the
streaming, voice and engine layers just to print `--help`.
"""

from __future__ import annotations

_LAZY_EXPORTS: dict[str, str] = {
    # cli.router
    "main": "genesis_architect_pro.cli.router",
    "_emit_hygiene_notice": "genesis_architect_pro.cli.router",
    # cli.parser
    "_build_parser": "genesis_architect_pro.cli.parser",
    # cli.formatting
    "_failure_modes_for": "genesis_architect_pro.cli.formatting",
    "_hr": "genesis_architect_pro.cli.formatting",
    "_jsonable": "genesis_architect_pro.cli.formatting",
    "_print_report_summary": "genesis_architect_pro.cli.formatting",
    "_prompt_approval": "genesis_architect_pro.cli.formatting",
    "_rich_approval": "genesis_architect_pro.cli.formatting",
    "_rich_classify": "genesis_architect_pro.cli.formatting",
    "_rich_commit": "genesis_architect_pro.cli.formatting",
    "_rich_header": "genesis_architect_pro.cli.formatting",
    "_rich_report": "genesis_architect_pro.cli.formatting",
    "_use_rich": "genesis_architect_pro.cli.formatting",
    # cli.session_cmds
    "cmd_decide": "genesis_architect_pro.cli.session_cmds",
    "cmd_explain": "genesis_architect_pro.cli.session_cmds",
    "cmd_harden": "genesis_architect_pro.cli.session_cmds",
    "cmd_recover": "genesis_architect_pro.cli.session_cmds",
    # cli.companion_cmds
    "cmd_companion": "genesis_architect_pro.cli.companion_cmds",
    "cmd_companion_listen": "genesis_architect_pro.cli.companion_cmds",
    "cmd_companion_serve": "genesis_architect_pro.cli.companion_cmds",
    "cmd_companion_ui": "genesis_architect_pro.cli.companion_cmds",
    # cli.voice_setup
    "NO_AUTO_INSTALL_ENV": "genesis_architect_pro.cli.voice_setup",
    "_auto_install_disabled": "genesis_architect_pro.cli.voice_setup",
    "_auto_setup_voice": "genesis_architect_pro.cli.voice_setup",
    "_companion_check": "genesis_architect_pro.cli.voice_setup",
    "_companion_setup": "genesis_architect_pro.cli.voice_setup",
    "_companion_speak": "genesis_architect_pro.cli.voice_setup",
    "_stdio_is_interactive": "genesis_architect_pro.cli.voice_setup",
    # cli.project_cmds
    "cmd_doctor": "genesis_architect_pro.cli.project_cmds",
    "cmd_engines": "genesis_architect_pro.cli.project_cmds",
    "cmd_memory": "genesis_architect_pro.cli.project_cmds",
    "cmd_purge": "genesis_architect_pro.cli.project_cmds",
    "cmd_ui": "genesis_architect_pro.cli.project_cmds",
    # cli.analysis_cmds
    "cmd_advise": "genesis_architect_pro.cli.analysis_cmds",
    "cmd_deps": "genesis_architect_pro.cli.analysis_cmds",
    "cmd_fetch": "genesis_architect_pro.cli.analysis_cmds",
    "cmd_gate": "genesis_architect_pro.cli.analysis_cmds",
    "cmd_sync": "genesis_architect_pro.cli.analysis_cmds",
    "cmd_telemetry": "genesis_architect_pro.cli.analysis_cmds",
}


def main(argv: list[str] | None = None) -> int:
    """The `genesis` console script.

    Defined rather than lazily re-exported: this is the declared entry point,
    and a real function keeps the import deferred to call time without relying
    on module `__getattr__` being consulted for it.
    """
    from genesis_architect_pro.cli.router import main as _main

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
