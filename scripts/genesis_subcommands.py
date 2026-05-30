"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/genesis_subcommands.py instead."""
from genesis_architect.core.genesis_subcommands import main

if __name__ == "__main__":
    raise SystemExit(main())
