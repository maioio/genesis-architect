"""Tests for security utilities."""
import pytest
from pathlib import Path
from src.python_cli.utils.security import get_safe_path, PathTraversalError


BASE = Path("/tmp/safe_base")


def test_safe_path_within_base(tmp_path):
    result = get_safe_path(tmp_path, "report.txt")
    assert result == (tmp_path / "report.txt").resolve()


def test_blocks_traversal(tmp_path):
    with pytest.raises(PathTraversalError):
        get_safe_path(tmp_path, "../etc/passwd")


def test_blocks_null_byte(tmp_path):
    with pytest.raises(PathTraversalError):
        get_safe_path(tmp_path, "file\x00.txt")


def test_raises_on_empty(tmp_path):
    with pytest.raises(ValueError):
        get_safe_path(tmp_path, "")
