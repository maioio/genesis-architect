"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/cache_engine.py instead."""
from genesis_architect.core.cache_engine import main

if __name__ == "__main__":
    raise SystemExit(main())
