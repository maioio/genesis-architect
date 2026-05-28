"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/issue_miner.py instead."""
from genesis_architect.core.issue_miner import main
if __name__ == "__main__":
    raise SystemExit(main())
