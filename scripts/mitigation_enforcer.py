"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/mitigation_enforcer.py instead."""
from genesis_architect.core.mitigation_enforcer import main, _is_substantive
if __name__ == "__main__":
    raise SystemExit(main())
