"""Tests for stdlib_filter - distinguishes stdlib imports from project/third-party."""
from genesis_architect.pro.stdlib_filter import is_stdlib_import, PYTHON_STDLIB


class TestIsStdlibImport:
    def test_common_stdlib_modules(self):
        for name in ("os", "sys", "json", "pathlib", "re", "dataclasses"):
            assert is_stdlib_import(name) is True, f"{name} should be stdlib"

    def test_dotted_name_uses_top_level(self):
        assert is_stdlib_import("os.path") is True
        assert is_stdlib_import("collections.abc") is True

    def test_third_party_not_stdlib(self):
        for name in ("anthropic", "pytest", "fastapi", "requests", "numpy"):
            assert is_stdlib_import(name) is False, f"{name} should not be stdlib"

    def test_project_internal_not_stdlib(self):
        assert is_stdlib_import("genesis_architect.pro") is False
        assert is_stdlib_import("genesis_architect.core.import_graph") is False

    def test_empty_string_is_not_stdlib(self):
        assert is_stdlib_import("") is False

    def test_stdlib_set_is_frozenset_and_populated(self):
        assert isinstance(PYTHON_STDLIB, frozenset)
        assert len(PYTHON_STDLIB) > 100  # 3.11 stdlib is large
        assert "os" in PYTHON_STDLIB


def test_future_is_stdlib():
    """`from __future__ import annotations` is not a third-party dependency.

    Omitting it put __future__ at the top of the dependency report for any
    modern codebase, since nearly every module imports it.
    """
    assert is_stdlib_import("__future__") is True
