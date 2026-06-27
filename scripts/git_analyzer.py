"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/git_analyzer.py instead."""
from genesis_architect.core.git_analyzer import main

if __name__ == "__main__":
    raise SystemExit(main())
