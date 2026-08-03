"""Console-script entry point for the ``genesis`` command.

Genesis has two command families that share one binary:

  * the scaffolding/research commands (``init``, ``research``, ``resolve``,
    ``publish``, ``config``, ``upgrade``) implemented with Typer in
    :mod:`genesis_architect.cli`, and
  * the decision-engine commands (``decide``, ``recover``, ``harden``,
    ``explain``, ``memory``, ``companion``, ``doctor``, ...) implemented with
    argparse in :mod:`genesis_architect.pro.gde_cli`.

``gde_cli.main`` is the unified dispatcher: it owns the engine commands and
delegates the scaffolding ones to the Typer app, so it is the single entry
point for the whole CLI.
"""

from __future__ import annotations

from genesis_architect.pro.gde_cli import main

__all__ = ["main"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
