"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/drift_detector.py instead."""
from genesis_architect.core.drift_detector import main

if __name__ == "__main__":
    raise SystemExit(main())
