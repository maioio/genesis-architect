"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/genesis_state.py instead."""
from genesis_architect.core.genesis_state import main
if __name__ == "__main__":
    raise SystemExit(main())
