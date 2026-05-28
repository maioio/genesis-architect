"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/env_probe.py instead."""
from genesis_architect.core.env_probe import main
if __name__ == "__main__":
    raise SystemExit(main())
