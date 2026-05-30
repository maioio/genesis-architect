"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/evidence_pack.py instead."""
from genesis_architect.core.evidence_pack import main

if __name__ == "__main__":
    raise SystemExit(main())
