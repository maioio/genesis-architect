"""Genesis engine CLI — parser, router, and command handlers.

gde_cli.py was a ~2000-line module holding the argument parser, ~20
command handlers, the shared Rich formatting helpers and the dispatcher.
Every one of its project imports was function-local and owned by exactly
one handler, so the split is a relocation rather than an untangling: each
handler took its own imports with it.

Named `commands` rather than `cli` on purpose. `genesis_architect.cli` is
already the Typer app for the scaffolding commands, and two sibling
modules named `cli` in one distribution is a readability hazard even
though the namespaces do not collide.

`genesis_architect.pro.gde_cli` remains the public entry point and still
exposes the names it always did.
"""
