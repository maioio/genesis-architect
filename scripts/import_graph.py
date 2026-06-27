"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/import_graph.py instead."""
from genesis_architect.core.import_graph import main

if __name__ == "__main__":
    raise SystemExit(main())
