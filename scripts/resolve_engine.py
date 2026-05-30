"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/resolve_engine.py instead."""
from genesis_architect.core.resolve_engine import resolve_with_output

if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:])
    print(resolve_with_output(query))
