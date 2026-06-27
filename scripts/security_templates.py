"""Shim: delegates to the installed package. Do not edit - edit src/genesis_architect/core/security_templates.py instead."""
from genesis_architect.core.security_templates import main

if __name__ == "__main__":
    raise SystemExit(main())
