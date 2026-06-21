"""Bridge from the free core to the optional Pro package.

The free core never depends on genesis-architect-pro. This bridge lets
free commands light up advanced behavior *when* Pro is installed and
licensed, and otherwise prints a friendly upgrade pointer. This is what
makes the split a true Open-Core: Pro extends the free CLI instead of
being a separate tool.
"""

from __future__ import annotations

import importlib

UPGRADE_URL = "https://github.com/maioio/genesis-architect"


class ProUnavailable(RuntimeError):
    """Raised when a Pro feature is requested but Pro is missing/unlicensed."""


def pro_installed() -> bool:
    """True if the genesis-architect-pro package is importable."""
    try:
        importlib.import_module("genesis_architect_pro")
        return True
    except Exception:
        return False


def pro_licensed() -> bool:
    """True if Pro is installed and a valid license is present."""
    if not pro_installed():
        return False
    try:
        lic = importlib.import_module("genesis_architect_pro.license")
        return bool(lic.is_licensed())
    except Exception:
        return False


def require_pro(feature: str) -> None:
    """Gate a free-CLI command that needs Pro. Raises ProUnavailable."""
    if pro_licensed():
        return
    if not pro_installed():
        raise ProUnavailable(
            f"'{feature}' is a Pro feature.\n"
            f"Install it:  pip install genesis-architect-pro\n"
            f"Learn more:  {UPGRADE_URL}"
        )
    raise ProUnavailable(
        f"'{feature}' needs a Pro license.\n"
        f"Set GENESIS_PRO_LICENSE=<your-key>.\n"
        f"Get a license:  {UPGRADE_URL}"
    )


def get_pro_module(name: str):
    """Import a Pro engine module by short name (e.g. 'video_research').

    Returns the module, or raises ProUnavailable with guidance.
    """
    require_pro(name)
    return importlib.import_module(f"genesis_architect_pro.{name}")
