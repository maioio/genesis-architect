"""Tests for the bridge to the advanced engine layer.

Genesis Architect no longer has a paid tier: the engines that used to ship as
a separate, license-gated `genesis-architect-pro` package now live in
`genesis_architect.pro` and are always available. These tests pin that down so
a paywall cannot quietly reappear through this module.
"""

import importlib

import pytest

from genesis_architect.core import pro_bridge


def test_engines_are_always_available():
    """The engines ship in this package - availability is not conditional."""
    assert importlib.util.find_spec("genesis_architect.pro") is not None
    assert pro_bridge.pro_installed() is True


def test_pro_licensed_is_a_backcompat_alias_of_availability():
    """`pro_licensed` is retained for old callers and must never gate."""
    assert pro_bridge.pro_licensed() is True


def test_require_pro_passes_by_default():
    pro_bridge.require_pro("video research")  # must not raise


def test_require_pro_raises_only_on_a_broken_install(monkeypatch):
    """The one legitimate failure mode left is a broken/partial install."""
    monkeypatch.setattr(pro_bridge, "pro_installed", lambda: False)
    with pytest.raises(pro_bridge.ProUnavailable) as exc:
        pro_bridge.require_pro("video research")
    message = str(exc.value)
    assert "broken or partial install" in message
    # It must not tell people to buy or install a separate Pro package.
    assert "genesis-architect-pro" not in message
    assert "license" not in message.lower()


def test_get_pro_module_imports_from_the_merged_package():
    mod = pro_bridge.get_pro_module("import_graph")
    assert mod.__name__ == "genesis_architect.pro.import_graph"


def test_get_pro_module_raises_when_install_is_broken(monkeypatch):
    monkeypatch.setattr(pro_bridge, "pro_installed", lambda: False)
    with pytest.raises(pro_bridge.ProUnavailable):
        pro_bridge.get_pro_module("video_research")
