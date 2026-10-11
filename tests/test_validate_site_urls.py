"""The own-site link validator must accept built pages and reject missing ones."""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "public_surface" / "validate_site_urls.py"
pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="scripts absent (container image)")


def _load():
    spec = importlib.util.spec_from_file_location("validate_site_urls", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_finds_absolute_and_root_relative_site_urls():
    m = _load()
    text = "[a](https://maioio.github.io/genesis-architect/capabilities/) [b](/genesis-architect/commands/#x)"
    assert m.find_urls(text) == [
        "https://maioio.github.io/genesis-architect/capabilities/",
        "https://maioio.github.io/genesis-architect/commands/",
    ]


def test_missing_page_fails_and_built_page_passes(tmp_path, monkeypatch):
    m = _load()
    (tmp_path / "capabilities").mkdir()
    (tmp_path / "capabilities" / "index.html").write_text("x")
    monkeypatch.setattr(m, "DIST", tmp_path)
    assert m.check_url("https://maioio.github.io/genesis-architect/capabilities/") is None
    assert "no built page" in m.check_url("https://maioio.github.io/genesis-architect/nope/")
