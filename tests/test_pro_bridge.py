"""Tests for the free-core -> Pro bridge."""

import importlib

import pytest

from genesis_architect.core import pro_bridge


def test_pro_not_installed_in_free_core():
    # In the free core test env, Pro should not be importable.
    if importlib.util.find_spec("genesis_architect_pro") is not None:
        pytest.skip("Pro is installed in this environment")
    assert pro_bridge.pro_installed() is False
    assert pro_bridge.pro_licensed() is False


def test_require_pro_raises_with_install_hint(monkeypatch):
    monkeypatch.setattr(pro_bridge, "pro_installed", lambda: False)
    monkeypatch.setattr(pro_bridge, "pro_licensed", lambda: False)
    with pytest.raises(pro_bridge.ProUnavailable) as exc:
        pro_bridge.require_pro("video research")
    assert "pip install genesis-architect-pro" in str(exc.value)


def test_require_pro_raises_license_hint_when_installed(monkeypatch):
    monkeypatch.setattr(pro_bridge, "pro_installed", lambda: True)
    monkeypatch.setattr(pro_bridge, "pro_licensed", lambda: False)
    with pytest.raises(pro_bridge.ProUnavailable) as exc:
        pro_bridge.require_pro("video research")
    assert "license" in str(exc.value).lower()


def test_require_pro_passes_when_licensed(monkeypatch):
    monkeypatch.setattr(pro_bridge, "pro_licensed", lambda: True)
    # Should not raise.
    pro_bridge.require_pro("video research")


def test_get_pro_module_raises_when_unavailable(monkeypatch):
    monkeypatch.setattr(pro_bridge, "pro_licensed", lambda: False)
    monkeypatch.setattr(pro_bridge, "pro_installed", lambda: False)
    with pytest.raises(pro_bridge.ProUnavailable):
        pro_bridge.get_pro_module("video_research")
