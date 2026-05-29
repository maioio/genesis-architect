"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/scaffold_generator.py instead."""
from genesis_architect.core.scaffold_generator import main, create_structure
if __name__ == "__main__":
    raise SystemExit(main())
