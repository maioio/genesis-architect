"""Genesis CLI — parser, router, and command handlers.

gde_cli.py was a 2000-line module holding the parser, ~20 command
handlers, the shared Rich formatting helpers and the dispatcher. Every
one of its 30 project imports was function-local and owned by exactly one
handler, so the split is a relocation rather than an untangling: each
handler took its own imports with it.

`genesis_architect_pro.gde_cli` remains the public entry point and still
exposes the names it always did.
"""
