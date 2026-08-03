"""Bridge to the advanced engine layer (``genesis_architect.pro``).

Genesis Architect used to ship as an open-core product: a free package plus a
paid, license-gated ``genesis-architect-pro`` add-on. That split is gone. Every
engine now ships in this one package, free and open source under AGPL-3.0.

This module is kept as a thin, stable indirection layer so the rest of the
codebase (and anyone who wrote code against it) keeps working. The advanced
engines are always installed and always available, so the availability checks
below simply report that.
"""

from __future__ import annotations

import importlib

PROJECT_URL = "https://github.com/maioio/genesis-architect"
UPGRADE_URL = PROJECT_URL  # back-compat alias; there is nothing to upgrade to


class ProUnavailable(RuntimeError):
    """Raised when an advanced engine module cannot be imported.

    With the packages merged this should only ever surface as a genuine
    installation problem (corrupt install, partial checkout) - never as a
    licensing or paywall condition.
    """


def pro_installed() -> bool:
    """True if the advanced engine layer is importable.

    Always true in a healthy install - the engines ship in this package.
    """
    try:
        importlib.import_module("genesis_architect.pro")
        return True
    except Exception:
        return False


def pro_licensed() -> bool:
    """Deprecated: there is no license tier any more.

    Kept so existing callers keep working; now just reports availability.
    """
    return pro_installed()


def require_pro(feature: str) -> None:
    """Ensure the advanced engines are importable before using ``feature``."""
    if pro_installed():
        return
    raise ProUnavailable(
        f"'{feature}' needs the genesis_architect.pro engines, which could not "
        f"be imported. This usually means a broken or partial install.\n"
        f"Try:     pip install --force-reinstall genesis-architect\n"
        f"Issues:  {PROJECT_URL}/issues"
    )


def get_pro_module(name: str):
    """Import an engine module by short name (e.g. 'video_research')."""
    require_pro(name)
    return importlib.import_module(f"genesis_architect.pro.{name}")
